// SPDX-License-Identifier: AGPL-3.0-or-later
//! Starts and monitors the local Python engine process.
//! Missing binaries fail closed: the desktop reports unavailable.
//! The WebView never receives the install bearer token.

use serde::Serialize;
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;

const CLIENT_VERSION: &str = "0.1.0";
const READY_TIMEOUT: Duration = Duration::from_secs(20);
const PROBE_TIMEOUT: Duration = Duration::from_secs(2);
const ENGINE_JSON_TIMEOUT: Duration = Duration::from_secs(30);
const CHAT_TURN_TIMEOUT: Duration = Duration::from_secs(300);
const INDEX_JOB_TIMEOUT: Duration = Duration::from_secs(180);
const TERMINAL_RUN_TIMEOUT: Duration = Duration::from_secs(90);

#[derive(Clone, Serialize)]
#[serde(tag = "status", rename_all = "camelCase")]
pub enum EngineUiState {
    Unavailable,
    Starting,
    Ready { version: String },
    Incompatible {
        #[serde(rename = "clientVersion")]
        client_version: String,
        #[serde(rename = "engineVersion")]
        engine_version: String,
    },
}

struct EngineConnection {
    base_url: String,
    token: String,
}

struct EngineInner {
    child: Option<Child>,
    connection: Option<EngineConnection>,
    ui_state: EngineUiState,
}

pub struct EngineSupervisor {
    inner: Arc<Mutex<EngineInner>>,
}

impl EngineSupervisor {
    pub fn spawn(app: &AppHandle) -> Self {
        let inner = Arc::new(Mutex::new(EngineInner {
            child: None,
            connection: None,
            ui_state: EngineUiState::Starting,
        }));
        let supervisor = Self {
            inner: Arc::clone(&inner),
        };
        let app_handle = app.clone();
        thread::spawn(move || run_sidecar(app_handle, inner));
        supervisor
    }

    pub fn probe(&self) -> EngineUiState {
        let connection = {
            let guard = match self.inner.lock() {
                Ok(guard) => guard,
                Err(_) => return EngineUiState::Unavailable,
            };
            match guard.connection.as_ref() {
                Some(connection) => EngineConnection {
                    base_url: connection.base_url.clone(),
                    token: connection.token.clone(),
                },
                None => return guard.ui_state.clone(),
            }
        };
        let next = probe_engine(&connection);
        if let Ok(mut guard) = self.inner.lock() {
            guard.ui_state = next.clone();
        }
        next
    }

    fn connection(&self) -> Option<EngineConnection> {
        let guard = self.inner.lock().ok()?;
        guard.connection.as_ref().map(|connection| EngineConnection {
            base_url: connection.base_url.clone(),
            token: connection.token.clone(),
        })
    }
}

impl Drop for EngineSupervisor {
    fn drop(&mut self) {
        if let Ok(mut inner) = self.inner.lock() {
            if let Some(child) = inner.child.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
            inner.child = None;
            inner.connection = None;
            inner.ui_state = EngineUiState::Unavailable;
        }
    }
}

#[tauri::command]
pub fn engine_state(state: State<EngineSupervisor>) -> EngineUiState {
    state.probe()
}

#[derive(Serialize)]
pub struct EngineJsonResponse {
    status: u16,
    body: String,
}

#[tauri::command]
pub fn engine_json(
    state: State<EngineSupervisor>,
    method: String,
    path: String,
    body: Option<serde_json::Value>,
) -> EngineJsonResponse {
    if !engine_path_allowed(&method, &path) {
        return EngineJsonResponse {
            status: 403,
            body: "{\"detail\":\"path not allowed\"}".to_string(),
        };
    }
    let Some(connection) = state.connection() else {
        return EngineJsonResponse {
            status: 0,
            body: String::new(),
        };
    };
    let auth = format!("Bearer {}", connection.token);
    let base = connection.base_url.trim_end_matches('/');
    let url = format!("{base}{path}");
    let payload = body.and_then(|value| {
        if value.is_null() {
            None
        } else {
            Some(value.to_string())
        }
    });
    let headers = [("Authorization", auth.as_str())];
    match loopback_request(
        &method,
        &url,
        &headers,
        payload.as_deref(),
        engine_json_timeout(&method, &path),
    ) {
        Ok((status, response_body)) => EngineJsonResponse {
            status,
            body: response_body,
        },
        Err(_) => EngineJsonResponse {
            status: 0,
            body: String::new(),
        },
    }
}

#[tauri::command]
pub async fn pick_repository_folder(app: AppHandle) -> Option<String> {
    app.dialog()
        .file()
        .set_title("Choose a git folder")
        .blocking_pick_folder()
        .map(|path| path.simplified().to_string())
}

#[tauri::command]
pub fn import_telegram_bot_token(
    app: AppHandle,
    state: State<EngineSupervisor>,
) -> EngineJsonResponse {
    let picked = app
        .dialog()
        .file()
        .set_title("Choose a Telegram bot token file")
        .blocking_pick_file();
    let Some(file) = picked else {
        return EngineJsonResponse {
            status: 0,
            body: String::new(),
        };
    };
    let path = file.simplified().to_string();
    let token = match fs::read_to_string(&path) {
        Ok(raw) => raw.trim().to_string(),
        Err(_) => {
            return EngineJsonResponse {
                status: 400,
                body: "{\"detail\":\"could not read token file\"}".to_string(),
            };
        }
    };
    if token.is_empty() {
        return EngineJsonResponse {
            status: 400,
            body: "{\"detail\":\"bot token is required\"}".to_string(),
        };
    }
    let Some(connection) = state.connection() else {
        return EngineJsonResponse {
            status: 0,
            body: String::new(),
        };
    };
    let auth = format!("Bearer {}", connection.token);
    let base = connection.base_url.trim_end_matches('/');
    let url = format!("{base}/telegram/token");
    let payload = serde_json::json!({ "token": token }).to_string();
    let headers = [("Authorization", auth.as_str())];
    match loopback_request("POST", &url, &headers, Some(payload.as_str()), ENGINE_JSON_TIMEOUT) {
        Ok((status, response_body)) => EngineJsonResponse {
            status,
            body: response_body,
        },
        Err(_) => EngineJsonResponse {
            status: 0,
            body: String::new(),
        },
    }
}

fn skill_memory_id_ok(id: &str) -> bool {
    !id.is_empty()
        && !id.contains('/')
        && id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-')
}

fn engine_path_allowed(method: &str, path: &str) -> bool {
    let path = path.split('?').next().unwrap_or(path);
    if path == "/github/status" || path == "/github/manifests" {
        return method == "GET";
    }
    if path == "/github/rulesets/propose" || path == "/github/rulesets/apply" {
        return method == "POST";
    }
    if let Some(rest) = path.strip_prefix("/github/apps/") {
        return method == "POST"
            && matches!(
                rest,
                "controller/convert"
                    | "reviewer/convert"
                    | "controller/install"
                    | "reviewer/install"
                    | "controller/verify"
                    | "reviewer/verify"
            );
    }
    if path == "/models" || path == "/models/" {
        return method == "GET";
    }
    if path == "/models/providers" {
        return method == "POST";
    }
    if path == "/models/assignments" {
        return method == "PUT";
    }
    if path == "/goals" || path == "/goals/" {
        return method == "GET" || method == "POST";
    }
    if path == "/goals/tick" || path == "/goals/tick/" {
        return method == "POST";
    }
    if path == "/goals/ingest" || path == "/goals/ingest/" {
        return method == "POST";
    }
    if let Some(rest) = path.strip_prefix("/goals/") {
        if let Some(id) = rest.strip_suffix("/plan") {
            return method == "POST"
                && !id.is_empty()
                && !id.contains('/')
                && id
                    .chars()
                    .all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-');
        }
        return method == "GET"
            && !rest.is_empty()
            && rest
                .chars()
                .all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-');
    }
    if path == "/runs" || path == "/runs/" {
        return method == "GET";
    }
    if path == "/events" || path == "/events/" {
        return method == "GET";
    }
    if path == "/skills" || path == "/skills/" {
        return method == "GET";
    }
    if path == "/skills/import" || path == "/skills/import/" {
        return method == "POST";
    }
    if path == "/skills/route" || path == "/skills/route/" {
        return method == "POST";
    }
    if let Some(rest) = path.strip_prefix("/skills/") {
        if let Some((id, action)) = rest.split_once('/') {
            return method == "POST"
                && skill_memory_id_ok(id)
                && matches!(action, "evaluate" | "approve" | "activate" | "disable" | "promote");
        }
        return method == "GET" && skill_memory_id_ok(rest);
    }
    if path == "/memory" || path == "/memory/" {
        return method == "GET";
    }
    if path == "/memory/import-lessons" || path == "/memory/import-lessons/" {
        return method == "POST";
    }
    if let Some(rest) = path.strip_prefix("/memory/") {
        return method == "GET" && skill_memory_id_ok(rest);
    }
    if path == "/chat/sessions" || path == "/chat/sessions/" {
        return method == "GET" || method == "POST";
    }
    if let Some(rest) = path.strip_prefix("/chat/sessions/") {
        if rest.is_empty() {
            return false;
        }
        if let Some((id, action)) = rest.split_once('/') {
            if method == "GET" {
                return match action.strip_prefix("images/") {
                    Some(image_id) => skill_memory_id_ok(id) && skill_memory_id_ok(image_id),
                    None => false,
                };
            }
            return method == "POST"
                && skill_memory_id_ok(id)
                && matches!(action, "messages" | "cancel");
        }
        return method == "GET" && skill_memory_id_ok(rest);
    }
    if path == "/telegram/status" || path == "/telegram/status/" {
        return method == "GET";
    }
    if path == "/telegram/allowlist" || path == "/telegram/allowlist/" {
        return method == "PUT";
    }
    if path == "/ops/dashboard"
        || path == "/ops/dashboard/"
        || path == "/ops/doctor"
        || path == "/ops/doctor/"
        || path == "/ops/dead-letters"
        || path == "/ops/dead-letters/"
        || path == "/ops/updates"
        || path == "/ops/updates/"
        || path == "/ops/notifications"
        || path == "/ops/notifications/"
    {
        return method == "GET";
    }
    if path == "/ops/settings" || path == "/ops/settings/" {
        return method == "GET" || method == "PUT";
    }
    if path == "/ops/backup"
        || path == "/ops/backup/"
        || path == "/ops/leases/recover"
        || path == "/ops/leases/recover/"
        || path == "/ops/rollback"
        || path == "/ops/rollback/"
    {
        return method == "POST";
    }
    if !path.starts_with("/repositories") {
        return false;
    }
    let rest = &path["/repositories".len()..];
    match (method, rest) {
        ("GET" | "POST", "" | "/") => true,
        ("POST", "/inspect") => true,
        (method, rest) if rest.starts_with('/') => {
            let trimmed = &rest[1..];
            let (id, suffix) = match trimmed.split_once('/') {
                Some((id, extra)) => (id, Some(extra)),
                None => (trimmed, None),
            };
            if id.is_empty()
                || !id
                    .chars()
                    .all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-')
            {
                return false;
            }
            matches!(
                (method, suffix),
                ("GET", None)
                    | ("GET", Some("preview"))
                    | ("GET", Some("index"))
                    | ("GET", Some("index/search"))
                    | ("GET", Some("index/map"))
                    | ("GET", Some("changes"))
                    | ("GET", Some("files"))
                    | ("GET", Some("files/contents"))
                    | ("PUT", Some("files/contents"))
                    | ("POST", Some("index/rebuild"))
                    | ("POST", Some("index/refresh"))
                    | ("POST", Some("commits"))
                    | ("POST", Some("writes/revert"))
                    | ("GET", Some("terminal/runs"))
                    | ("POST", Some("terminal/runs"))
                    | ("POST", Some("terminal/runs/cancel"))
                    | ("POST", Some("terminal/sessions"))
                    | ("POST", Some("terminal/sessions/input"))
                    | ("POST", Some("pause" | "disable" | "remove" | "re-enrol" | "resume"))
            )
        }
        _ => false,
    }
}

fn run_sidecar(app: AppHandle, inner: Arc<Mutex<EngineInner>>) {
    match spawn_engine(&app) {
        Ok((child, connection)) => {
            if let Ok(mut guard) = inner.lock() {
                guard.child = Some(child);
                guard.connection = Some(connection);
            }
            monitor_child(inner);
        }
        Err(error) => {
            eprintln!("Kronos engine sidecar did not start: {error}");
            if let Ok(mut guard) = inner.lock() {
                guard.ui_state = EngineUiState::Unavailable;
            }
        }
    }
}

fn monitor_child(inner: Arc<Mutex<EngineInner>>) {
    loop {
        thread::sleep(Duration::from_millis(250));
        let mut guard = match inner.lock() {
            Ok(guard) => guard,
            Err(_) => break,
        };
        let Some(child) = guard.child.as_mut() else {
            break;
        };
        match child.try_wait() {
            Ok(Some(_)) | Err(_) => {
                guard.child = None;
                guard.connection = None;
                guard.ui_state = EngineUiState::Unavailable;
                break;
            }
            Ok(None) => {}
        }
    }
}

fn spawn_engine(app: &AppHandle) -> Result<(Child, EngineConnection), String> {
    let paths = EngineDirs::resolve(app)?;
    paths.create()?;
    let token = load_or_create_token(&paths.config.join("install.json"))?;
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
        .env("KRONOS_BIND_PORT", "0")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(src) = engine_src_dir() {
        let sep = if cfg!(windows) { ';' } else { ':' };
        let merged = match std::env::var("PYTHONPATH") {
            Ok(existing) if !existing.is_empty() => {
                format!("{}{}{}", src.display(), sep, existing)
            }
            _ => src.display().to_string(),
        };
        command.env("PYTHONPATH", merged);
    }

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command.spawn().map_err(|error| {
        format!("failed to spawn engine ({program:?} {args:?}): {error}")
    })?;

    let (ready_tx, ready_rx) = mpsc::channel();
    wait_for_ready_then_log(child.stdout.take(), log_file.try_clone().ok(), ready_tx);
    capture_logs(child.stderr.take(), Some(log_file));

    let base_url = match ready_rx.recv_timeout(READY_TIMEOUT) {
        Ok(Ok(url)) => url,
        Ok(Err(error)) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
        Err(_) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err("timed out waiting for KRONOS_READY".to_string());
        }
    };

    Ok((
        child,
        EngineConnection {
            base_url,
            token,
        },
    ))
}

fn engine_src_dir() -> Option<PathBuf> {
    if let Ok(raw) = std::env::var("KRONOS_ENGINE_SRC") {
        let path = PathBuf::from(raw);
        if path.join("kronos_engine").is_dir() {
            return Some(path);
        }
    }
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo = manifest.parent()?.parent()?.parent()?;
    let src = repo.join("engine").join("src");
    src.join("kronos_engine").is_dir().then_some(src)
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
            data: resolver
                .app_local_data_dir()
                .map_err(|error| error.to_string())?,
            config: resolver
                .app_config_dir()
                .map_err(|error| error.to_string())?,
            cache: resolver.app_cache_dir().map_err(|error| error.to_string())?,
            logs: resolver.app_log_dir().map_err(|error| error.to_string())?,
        })
    }

    fn create(&self) -> Result<(), String> {
        for directory in [&self.data, &self.config, &self.cache, &self.logs] {
            fs::create_dir_all(directory).map_err(|error| error.to_string())?;
        }
        fs::create_dir_all(self.cache.join("worktrees")).map_err(|error| error.to_string())?;
        fs::create_dir_all(self.cache.join("indexes")).map_err(|error| error.to_string())?;
        Ok(())
    }
}

fn engine_command() -> Result<(PathBuf, Vec<String>), String> {
    if let Ok(bin) = std::env::var("KRONOS_ENGINE_BIN") {
        let path = PathBuf::from(bin);
        if path.exists() {
            return Ok((path, Vec::new()));
        }
        return Err(format!(
            "KRONOS_ENGINE_BIN does not exist: {}",
            path.display()
        ));
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
    let token = generate_token()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let body = serde_json::json!({ "auth_token": token }).to_string();
    write_secret_file(path, body.as_bytes())?;
    Ok(token)
}

fn generate_token() -> Result<String, String> {
    let bytes = csprng_bytes()?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn csprng_bytes() -> Result<[u8; 32], String> {
    let mut bytes = [0u8; 32];
    fill_csprng(&mut bytes)?;
    Ok(bytes)
}

#[cfg(unix)]
fn fill_csprng(bytes: &mut [u8]) -> Result<(), String> {
    File::open("/dev/urandom")
        .and_then(|mut file| file.read_exact(bytes))
        .map_err(|error| error.to_string())
}

#[cfg(windows)]
fn fill_csprng(bytes: &mut [u8]) -> Result<(), String> {
    let status = unsafe { SystemFunction036(bytes.as_mut_ptr(), bytes.len() as u32) };
    if status == 0 {
        return Err("RtlGenRandom failed".to_string());
    }
    Ok(())
}

#[cfg(windows)]
#[link(name = "advapi32")]
unsafe extern "system" {
    fn SystemFunction036(random_buffer: *mut u8, random_buffer_length: u32) -> u8;
}

fn probe_engine(connection: &EngineConnection) -> EngineUiState {
    let auth = format!("Bearer {}", connection.token);
    let base = connection.base_url.trim_end_matches('/');
    let health_body = match loopback_get(
        &format!("{base}/health"),
        &[("Authorization", auth.as_str())],
    ) {
        Ok((200, body)) => body,
        _ => return EngineUiState::Unavailable,
    };
    let health_json: serde_json::Value = match serde_json::from_str(&health_body) {
        Ok(body) => body,
        Err(_) => return EngineUiState::Unavailable,
    };
    if health_json.get("status").and_then(|value| value.as_str()) != Some("ok") {
        return EngineUiState::Unavailable;
    }

    let version_body = match loopback_get(
        &format!("{base}/version"),
        &[
            ("Authorization", auth.as_str()),
            ("X-Kronos-Client-Version", CLIENT_VERSION),
        ],
    ) {
        Ok((200, body)) => body,
        _ => return EngineUiState::Unavailable,
    };
    let body: serde_json::Value = match serde_json::from_str(&version_body) {
        Ok(body) => body,
        Err(_) => return EngineUiState::Unavailable,
    };
    let engine_version = body
        .get("engine_version")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    if body.get("compatible").and_then(|value| value.as_bool()) != Some(true) {
        return EngineUiState::Incompatible {
            client_version: CLIENT_VERSION.to_string(),
            engine_version: if engine_version.is_empty() {
                "unknown".to_string()
            } else {
                engine_version.to_string()
            },
        };
    }
    if engine_version.is_empty() {
        return EngineUiState::Unavailable;
    }
    EngineUiState::Ready {
        version: engine_version.to_string(),
    }
}

struct LoopbackUrl {
    host: String,
    port: u16,
    path: String,
}

fn parse_loopback_http_url(url: &str) -> Result<LoopbackUrl, String> {
    let rest = url
        .strip_prefix("http://")
        .ok_or_else(|| "engine probe requires http".to_string())?;
    let (hostport, path) = rest.split_once('/').unwrap_or((rest, ""));
    let path = if path.is_empty() {
        "/".to_string()
    } else {
        format!("/{path}")
    };
    let (host, port_raw) = hostport
        .rsplit_once(':')
        .ok_or_else(|| "engine probe URL is missing a port".to_string())?;
    let port: u16 = port_raw
        .parse()
        .map_err(|_| "engine probe URL has an invalid port".to_string())?;
    Ok(LoopbackUrl {
        host: host.to_string(),
        port,
        path,
    })
}

fn loopback_get(url: &str, extra_headers: &[(&str, &str)]) -> Result<(u16, String), String> {
    loopback_request("GET", url, extra_headers, None, PROBE_TIMEOUT)
}

fn engine_json_timeout(method: &str, path: &str) -> Duration {
    let normalized = path.split('?').next().unwrap_or(path).trim_end_matches('/');
    if normalized.ends_with("/messages") {
        return CHAT_TURN_TIMEOUT;
    }
    if normalized.ends_with("/index/rebuild") || normalized.ends_with("/index/refresh") {
        return INDEX_JOB_TIMEOUT;
    }
    if method == "POST" && normalized.ends_with("/terminal/runs") {
        return TERMINAL_RUN_TIMEOUT;
    }
    if method == "POST" || method == "PUT" {
        return ENGINE_JSON_TIMEOUT;
    }
    PROBE_TIMEOUT
}

fn loopback_request(
    method: &str,
    url: &str,
    extra_headers: &[(&str, &str)],
    body: Option<&str>,
    timeout: Duration,
) -> Result<(u16, String), String> {
    let parsed = parse_loopback_http_url(url)?;
    let mut stream = TcpStream::connect((parsed.host.as_str(), parsed.port))
        .map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(timeout))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(timeout))
        .map_err(|error| error.to_string())?;
    let payload = body.unwrap_or("");
    let mut request = format!(
        "{} {} HTTP/1.1\r\nHost: {}:{}\r\nConnection: close\r\n",
        method, parsed.path, parsed.host, parsed.port
    );
    for (name, value) in extra_headers {
        request.push_str(name);
        request.push_str(": ");
        request.push_str(value);
        request.push_str("\r\n");
    }
    if !payload.is_empty() {
        request.push_str("Content-Type: application/json\r\n");
        request.push_str(&format!("Content-Length: {}\r\n", payload.len()));
    }
    request.push_str("\r\n");
    request.push_str(payload);
    stream
        .write_all(request.as_bytes())
        .map_err(|error| error.to_string())?;
    let mut raw = Vec::new();
    stream
        .read_to_end(&mut raw)
        .map_err(|error| error.to_string())?;
    parse_http_response(&raw)
}

fn parse_http_response(raw: &[u8]) -> Result<(u16, String), String> {
    let text = String::from_utf8_lossy(raw);
    let (header, body) = text
        .split_once("\r\n\r\n")
        .or_else(|| text.split_once("\n\n"))
        .ok_or_else(|| "engine probe response was truncated".to_string())?;
    let status_line = header.lines().next().unwrap_or("");
    let status: u16 = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|item| item.parse().ok())
        .ok_or_else(|| "engine probe response had no status".to_string())?;
    Ok((status, body.to_string()))
}

fn write_secret_file(path: &Path, body: &[u8]) -> Result<(), String> {
    let mut options = OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(path).map_err(|error| error.to_string())?;
    file.write_all(body).map_err(|error| error.to_string())?;
    file.sync_all().map_err(|error| error.to_string())?;
    #[cfg(windows)]
    restrict_windows_owner_only(path)?;
    Ok(())
}

#[cfg(windows)]
fn restrict_windows_owner_only(path: &Path) -> Result<(), String> {
    let path_arg = path.to_string_lossy().into_owned();
    let user = match std::env::var("USERNAME") {
        Ok(name) if !name.is_empty() => name,
        _ => return Ok(()),
    };
    let grant = format!("{user}:(F)");
    let _ = Command::new("icacls")
        .args([&path_arg, "/grant:r", &grant, "/inheritance:r"])
        .output();
    Ok(())
}

fn wait_for_ready_then_log<R>(
    stream: Option<R>,
    log_file: Option<File>,
    ready_tx: mpsc::Sender<Result<String, String>>,
) where
    R: Read + Send + 'static,
{
    let Some(stream) = stream else {
        let _ = ready_tx.send(Err("engine stdout was not piped".to_string()));
        return;
    };
    thread::spawn(move || {
        let reader = BufReader::new(stream);
        let mut log_file = log_file;
        let mut announced = false;
        for line in reader.lines().map_while(Result::ok) {
            if !announced {
                if let Some(url) = line.strip_prefix("KRONOS_READY ") {
                    announced = true;
                    let _ = ready_tx.send(Ok(url.trim().to_string()));
                }
            }
            if let Some(file) = log_file.as_mut() {
                let _ = writeln!(file, "{line}");
            }
        }
        if !announced {
            let _ = ready_tx.send(Err(
                "engine closed stdout before KRONOS_READY".to_string()
            ));
        }
    });
}

fn capture_logs<R>(stream: Option<R>, log_file: Option<File>)
where
    R: Read + Send + 'static,
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

#[cfg(test)]
mod tests {
    use super::engine_path_allowed;

    #[test]
    fn allowlist_includes_models_and_repositories() {
        assert!(engine_path_allowed("GET", "/models"));
        assert!(engine_path_allowed("POST", "/models/providers"));
        assert!(engine_path_allowed("PUT", "/models/assignments"));
        assert!(!engine_path_allowed("GET", "/models/assignments"));
        assert!(!engine_path_allowed("POST", "/secrets"));
        assert!(engine_path_allowed("GET", "/github/status"));
        assert!(engine_path_allowed("GET", "/github/manifests"));
        assert!(engine_path_allowed("POST", "/github/apps/controller/convert"));
        assert!(engine_path_allowed("POST", "/github/apps/reviewer/verify"));
        assert!(!engine_path_allowed("POST", "/github/apps/controller"));
        assert!(engine_path_allowed("POST", "/github/rulesets/propose"));
        assert!(engine_path_allowed("POST", "/github/rulesets/apply"));
        assert!(!engine_path_allowed("GET", "/github/apps/controller"));
        assert!(engine_path_allowed("GET", "/repositories"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/index"));
        assert!(engine_path_allowed(
            "GET",
            "/repositories/repo_alpha/index/search?q=connect"
        ));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/index/rebuild"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/index/refresh"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/index/map"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/files"));
        assert!(engine_path_allowed(
            "GET",
            "/repositories/repo_alpha/files/contents?path=src%2Fapp.py"
        ));
        assert!(engine_path_allowed(
            "PUT",
            "/repositories/repo_alpha/files/contents"
        ));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/changes"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/commits"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/writes/revert"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/terminal/runs"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/terminal/runs"));
        assert!(engine_path_allowed(
            "POST",
            "/repositories/repo_alpha/terminal/runs/cancel"
        ));
        assert!(engine_path_allowed(
            "POST",
            "/repositories/repo_alpha/terminal/sessions"
        ));
        assert!(engine_path_allowed(
            "POST",
            "/repositories/repo_alpha/terminal/sessions/input"
        ));
        assert!(!engine_path_allowed("DELETE", "/repositories/repo_alpha/index"));
        assert!(engine_path_allowed("GET", "/goals"));
        assert!(engine_path_allowed("POST", "/goals"));
        assert!(engine_path_allowed("GET", "/goals/goal_abc"));
        assert!(engine_path_allowed("POST", "/goals/goal_abc/plan"));
        assert!(engine_path_allowed("POST", "/goals/tick"));
        assert!(engine_path_allowed("POST", "/goals/ingest"));
        assert!(engine_path_allowed("GET", "/runs"));
        assert!(engine_path_allowed("GET", "/events?after=0"));
        assert!(!engine_path_allowed("DELETE", "/goals"));
        assert!(engine_path_allowed("GET", "/skills"));
        assert!(engine_path_allowed("POST", "/skills/import"));
        assert!(engine_path_allowed("POST", "/skills/route"));
        assert!(engine_path_allowed("POST", "/skills/skill-tdd-core/evaluate"));
        assert!(engine_path_allowed("POST", "/skills/skill-tdd-core/approve"));
        assert!(engine_path_allowed("POST", "/skills/skill-tdd-core/activate"));
        assert!(engine_path_allowed("POST", "/skills/skill-tdd-core/disable"));
        assert!(engine_path_allowed("POST", "/skills/skill-tdd-core/promote"));
        assert!(engine_path_allowed("GET", "/skills/skill-tdd-core"));
        assert!(!engine_path_allowed("DELETE", "/skills/skill-tdd-core"));
        assert!(engine_path_allowed("GET", "/memory"));
        assert!(engine_path_allowed("POST", "/memory/import-lessons"));
        assert!(engine_path_allowed("GET", "/memory/mem-1"));
        assert!(!engine_path_allowed("DELETE", "/memory"));
        assert!(engine_path_allowed("GET", "/telegram/status"));
        assert!(engine_path_allowed("PUT", "/telegram/allowlist"));
        assert!(!engine_path_allowed("POST", "/telegram/token"));
        assert!(!engine_path_allowed("POST", "/telegram/poll"));
        assert!(engine_path_allowed("GET", "/ops/dashboard"));
        assert!(engine_path_allowed("GET", "/ops/doctor"));
        assert!(engine_path_allowed("POST", "/ops/backup"));
        assert!(engine_path_allowed("GET", "/ops/dead-letters"));
        assert!(engine_path_allowed("POST", "/ops/leases/recover"));
        assert!(engine_path_allowed("GET", "/ops/settings"));
        assert!(engine_path_allowed("PUT", "/ops/settings"));
        assert!(engine_path_allowed("GET", "/ops/updates"));
        assert!(engine_path_allowed("GET", "/ops/notifications"));
        assert!(engine_path_allowed("POST", "/ops/rollback"));
        assert!(!engine_path_allowed("POST", "/ops/token"));
        assert!(!engine_path_allowed("POST", "/ops/pem"));
        assert!(engine_path_allowed("GET", "/chat/sessions"));
        assert!(engine_path_allowed("POST", "/chat/sessions"));
        assert!(engine_path_allowed("GET", "/chat/sessions/chat_1"));
        assert!(engine_path_allowed("POST", "/chat/sessions/chat_1/messages"));
        assert!(engine_path_allowed("POST", "/chat/sessions/chat_1/cancel"));
        assert!(engine_path_allowed("GET", "/chat/sessions/chat_1/images/img_abc"));
        assert!(!engine_path_allowed("POST", "/chat/sessions/chat_1/images/img_abc"));
        assert!(!engine_path_allowed("GET", "/chat/sessions/chat_1/images/../secret"));
        assert!(!engine_path_allowed("DELETE", "/chat/sessions/chat_1"));
    }

    #[test]
    fn chat_turns_use_a_long_read_timeout() {
        use super::{engine_json_timeout, PROBE_TIMEOUT};
        use std::time::Duration;
        assert!(
            engine_json_timeout("POST", "/chat/sessions/chat_1/messages")
                >= Duration::from_secs(120)
        );
        assert_eq!(
            engine_json_timeout("GET", "/ops/doctor"),
            PROBE_TIMEOUT
        );
        assert!(
            engine_json_timeout("POST", "/repositories/repo_alpha/terminal/runs")
                >= Duration::from_secs(60)
        );
        assert_eq!(
            engine_json_timeout("GET", "/repositories/repo_alpha/terminal/runs"),
            PROBE_TIMEOUT
        );
    }
}
