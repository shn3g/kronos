// SPDX-License-Identifier: AGPL-3.0-or-later
//! Starts and monitors the local Python engine process.
//! Missing binaries fail closed: the desktop reports unavailable.

use serde::Serialize;
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, State};

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineConnection {
    pub base_url: String,
    pub token: String,
}

struct EngineInner {
    child: Option<Child>,
    connection: Option<EngineConnection>,
}

pub struct EngineSupervisor {
    inner: Mutex<EngineInner>,
}

impl EngineSupervisor {
    pub fn spawn(app: &AppHandle) -> Self {
        let supervisor = Self {
            inner: Mutex::new(EngineInner {
                child: None,
                connection: None,
            }),
        };
        match spawn_engine(app) {
            Ok((child, connection)) => {
                if let Ok(mut inner) = supervisor.inner.lock() {
                    inner.child = Some(child);
                    inner.connection = Some(connection);
                }
            }
            Err(error) => {
                eprintln!("Kronos engine sidecar did not start: {error}");
            }
        }
        supervisor
    }

    pub fn connection(&self) -> Option<EngineConnection> {
        self.inner
            .lock()
            .ok()
            .and_then(|inner| inner.connection.clone())
    }
}

impl Drop for EngineSupervisor {
    fn drop(&mut self) {
        if let Ok(mut inner) = self.inner.lock() {
            if let Some(child) = inner.child.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

#[tauri::command]
pub fn engine_connection(state: State<EngineSupervisor>) -> Option<EngineConnection> {
    state.connection()
}

fn spawn_engine(app: &AppHandle) -> Result<(Child, EngineConnection), String> {
    let paths = EngineDirs::resolve(app)?;
    paths.create()?;
    let token = load_or_create_token(&paths.config.join("install.json"))?;
    let port = free_loopback_port()?;
    let base_url = format!("http://127.0.0.1:{port}");
    let (program, args) = engine_command()?;
    let log_path = paths.logs.join("engine.log");
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .write(true)
        .open(&log_path)
        .map_err(|error| error.to_string())?;

    let mut command = Command::new(&program);
    command
        .args(&args)
        .env("KRONOS_DATA_HOME", &paths.data)
        .env("KRONOS_CONFIG_HOME", &paths.config)
        .env("KRONOS_CACHE_HOME", &paths.cache)
        .env("KRONOS_LOG_HOME", &paths.logs)
        .env("KRONOS_AUTH_TOKEN", &token)
        .env("KRONOS_BIND_HOST", "127.0.0.1")
        .env("KRONOS_BIND_PORT", port.to_string())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command.spawn().map_err(|error| {
        format!("failed to spawn engine ({program:?} {args:?}): {error}")
    })?;
    capture_logs(child.stdout.take(), log_file.try_clone().ok());
    capture_logs(child.stderr.take(), Some(log_file));

    Ok((
        child,
        EngineConnection {
            base_url,
            token,
        },
    ))
}

struct EngineDirs {
    data: PathBuf,
    config: PathBuf,
    cache: PathBuf,
    logs: PathBuf,
}

impl EngineDirs {
    fn resolve(app: &AppHandle) -> Result<Self, String> {
        let resolver = app.path();
        Ok(Self {
            data: resolver.app_local_data_dir().map_err(|error| error.to_string())?,
            config: resolver.app_config_dir().map_err(|error| error.to_string())?,
            cache: resolver.app_cache_dir().map_err(|error| error.to_string())?,
            logs: resolver.app_log_dir().map_err(|error| error.to_string())?,
        })
    }

    fn create(&self) -> Result<(), String> {
        for directory in [&self.data, &self.config, &self.cache, &self.logs] {
            fs::create_dir_all(directory).map_err(|error| error.to_string())?;
        }
        fs::create_dir_all(self.cache.join("worktrees")).map_err(|error| error.to_string())?;
        Ok(())
    }
}

fn engine_command() -> Result<(PathBuf, Vec<String>), String> {
    if let Ok(bin) = std::env::var("KRONOS_ENGINE_BIN") {
        let path = PathBuf::from(bin);
        if path.exists() {
            return Ok((path, Vec::new()));
        }
        return Err(format!("KRONOS_ENGINE_BIN does not exist: {}", path.display()));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            for name in ["kronos-engine.exe", "kronos-engine"] {
                let candidate = dir.join(name);
                if candidate.exists() {
                    return Ok((candidate, Vec::new()));
                }
            }
        }
    }
    let python = python_executable();
    Ok((
        PathBuf::from(python),
        vec!["-m".to_string(), "kronos_engine".to_string()],
    ))
}

fn python_executable() -> &'static str {
    if cfg!(windows) {
        "python"
    } else {
        "python3"
    }
}

fn free_loopback_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|error| error.to_string())?;
    Ok(listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port())
}

fn load_or_create_token(path: &Path) -> Result<String, String> {
    if let Ok(raw) = fs::read_to_string(path) {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&raw) {
            if let Some(token) = value.get("auth_token").and_then(|item| item.as_str()) {
                if !token.is_empty() {
                    return Ok(token.to_string());
                }
            }
        }
    }
    let token = generate_token();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let body = serde_json::json!({ "auth_token": token });
    fs::write(path, body.to_string()).map_err(|error| error.to_string())?;
    Ok(token)
}

fn generate_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    format!("kronos-{:x}-{:x}", std::process::id(), nanos)
}

fn capture_logs<R>(stream: Option<R>, log_file: Option<File>)
where
    R: std::io::Read + Send + 'static,
{
    let Some(stream) = stream else {
        return;
    };
    let Some(mut log_file) = log_file else {
        return;
    };
    thread::spawn(move || {
        let reader = BufReader::new(stream);
        for line in reader.lines().map_while(Result::ok) {
            let _ = writeln!(log_file, "{line}");
        }
    });
}
