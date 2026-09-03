// SPDX-License-Identifier: AGPL-3.0-or-later
//! Starts and monitors the local Python engine process.
//! Missing binaries fail closed: the desktop reports unavailable.
//! The WebView never receives the install bearer token.

use serde::Serialize;
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, ErrorKind, Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;

const CLIENT_VERSION: &str = "0.5.1";
const READY_TIMEOUT: Duration = Duration::from_secs(20);
const PROBE_TIMEOUT: Duration = Duration::from_secs(2);
const ENGINE_JSON_TIMEOUT: Duration = Duration::from_secs(30);
const ENGINE_JSON_GET_TIMEOUT: Duration = Duration::from_secs(8);
const INDEX_JOB_TIMEOUT: Duration = Duration::from_secs(180);
const TERMINAL_RUN_TIMEOUT: Duration = Duration::from_secs(90);
const STREAM_READ_POLL: Duration = Duration::from_millis(200);
const STREAM_MAX_IDLE: Duration = Duration::from_secs(300);
const ENGINE_STREAM_EVENT: &str = "engine-stream";

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

#[derive(Clone)]
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

#[derive(Clone, Default)]
pub struct StreamCancels {
    inner: Arc<Mutex<HashSet<String>>>,
}

impl StreamCancels {
    fn cancel(&self, request_id: &str) {
        if let Ok(mut guard) = self.inner.lock() {
            guard.insert(request_id.to_string());
        }
    }

    fn is_cancelled(&self, request_id: &str) -> bool {
        self.inner
            .lock()
            .map(|guard| guard.contains(request_id))
            .unwrap_or(false)
    }

    fn finish(&self, request_id: &str) {
        if let Ok(mut guard) = self.inner.lock() {
            guard.remove(request_id);
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct EngineStreamEvent {
    request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    delta: Option<String>,
    done: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    citations: Option<Vec<StreamCitation>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    goal_refs: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    goal: Option<serde_json::Value>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct StreamCitation {
    path: String,
    start_line: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    end_line: Option<u32>,
}

#[derive(Debug, Clone, PartialEq)]
enum SseDataEvent {
    Delta(String),
    Tool(serde_json::Value),
    Goal(serde_json::Value),
    Error(String),
    Done {
        content: String,
        citations: Vec<StreamCitation>,
        goal_refs: Vec<String>,
    },
}

#[tauri::command]
pub async fn engine_stream(
    app: AppHandle,
    state: State<'_, EngineSupervisor>,
    cancels: State<'_, StreamCancels>,
    method: String,
    path: String,
    body: Option<serde_json::Value>,
    request_id: String,
) -> Result<(), String> {
    // Tauri 2: async commands that take State<'_> (a reference) must return Result,
    // or generate_handler! omits the command and the crate does not compile.
    let supervisor = state.inner().clone();
    let cancels = cancels.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_engine_stream(
            &app,
            &supervisor,
            &cancels,
            &method,
            &path,
            body.as_ref(),
            &request_id,
        );
    })
    .await
    .map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn engine_stream_cancel(cancels: State<StreamCancels>, request_id: String) {
    cancels.cancel(&request_id);
}

fn run_engine_stream(
    app: &AppHandle,
    supervisor: &EngineSupervisor,
    cancels: &StreamCancels,
    method: &str,
    path: &str,
    body: Option<&serde_json::Value>,
    request_id: &str,
) {
    let emit_error = |message: String| {
        emit_stream(
            app,
            EngineStreamEvent {
                request_id: request_id.to_string(),
                delta: None,
                done: true,
                error: Some(message),
                content: None,
                citations: None,
                goal_refs: None,
                tool: None,
                goal: None,
            },
        );
    };
    if !engine_path_allowed(method, path) {
        emit_error("path not allowed".to_string());
        cancels.finish(request_id);
        return;
    }
    let Some(connection) = supervisor.connection() else {
        emit_error("engine unavailable".to_string());
        cancels.finish(request_id);
        return;
    };
    let result = stream_loopback(
        app,
        &connection,
        cancels,
        method,
        path,
        body,
        request_id,
    );
    match result {
        Ok(()) => {}
        Err(message) if message == "cancelled" => {
            emit_stream(
                app,
                EngineStreamEvent {
                    request_id: request_id.to_string(),
                    delta: None,
                    done: true,
                    error: None,
                    content: None,
                    citations: None,
                    goal_refs: None,
                    tool: None,
                    goal: None,
                },
            );
        }
        Err(message) => emit_error(message),
    }
    cancels.finish(request_id);
}

fn stream_loopback(
    app: &AppHandle,
    connection: &EngineConnection,
    cancels: &StreamCancels,
    method: &str,
    path: &str,
    body: Option<&serde_json::Value>,
    request_id: &str,
) -> Result<(), String> {
    let parsed = parse_loopback_http_url(&format!(
        "{}{}",
        connection.base_url.trim_end_matches('/'),
        path
    ))?;
    let mut stream = TcpStream::connect((parsed.host.as_str(), parsed.port))
        .map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(STREAM_READ_POLL))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(PROBE_TIMEOUT))
        .map_err(|error| error.to_string())?;
    let payload = body
        .and_then(|value| {
            if value.is_null() {
                None
            } else {
                Some(value.to_string())
            }
        })
        .unwrap_or_default();
    let auth = format!("Bearer {}", connection.token);
    let mut request = format!(
        "{} {} HTTP/1.1\r\nHost: {}:{}\r\nConnection: close\r\nAccept: text/event-stream\r\nAuthorization: {}\r\n",
        method, parsed.path, parsed.host, parsed.port, auth
    );
    if !payload.is_empty() {
        request.push_str("Content-Type: application/json\r\n");
        request.push_str(&format!("Content-Length: {}\r\n", payload.len()));
    }
    request.push_str("\r\n");
    request.push_str(&payload);
    stream
        .write_all(request.as_bytes())
        .map_err(|error| error.to_string())?;

    let cancelled = || cancels.is_cancelled(request_id);
    let (status, headers, leftover) = read_http_head(&mut stream, &cancelled)?;
    let chunked = headers.iter().any(|(name, value)| {
        name.eq_ignore_ascii_case("transfer-encoding") && value.to_ascii_lowercase().contains("chunked")
    });
    if status != 200 {
        let body = read_remaining_body(&mut stream, leftover, chunked, &cancelled)?;
        return Err(detail_from_body(status, &body));
    }

    let mut decoder = if chunked {
        Some(ChunkDecoder::default())
    } else {
        None
    };
    let mut sse_buf = String::new();
    let mut completed = false;
    {
        let mut push_bytes = |bytes: &[u8]| -> Result<(), String> {
            let decoded = if let Some(decoder) = decoder.as_mut() {
                decoder.push(bytes)?
            } else {
                bytes.to_vec()
            };
            if decoded.is_empty() {
                return Ok(());
            }
            sse_buf.push_str(&String::from_utf8_lossy(&decoded));
            for event in drain_sse_events(&mut sse_buf) {
                if matches!(event, SseDataEvent::Done { .. } | SseDataEvent::Error(_)) {
                    completed = true;
                }
                emit_sse(app, request_id, event);
            }
            Ok(())
        };
        if !leftover.is_empty() {
            push_bytes(&leftover)?;
        }

        let mut buf = [0u8; 4096];
        let mut last_data = Instant::now();
        loop {
            if cancelled() {
                return Err("cancelled".to_string());
            }
            if last_data.elapsed() > STREAM_MAX_IDLE {
                return Err("timed out reading the orchestrator stream".to_string());
            }
            match stream.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    last_data = Instant::now();
                    push_bytes(&buf[..n])?;
                }
                Err(error) if matches!(error.kind(), ErrorKind::TimedOut | ErrorKind::WouldBlock) => {
                    continue;
                }
                Err(error) => return Err(error.to_string()),
            }
        }
    }
    if !sse_buf.is_empty() {
        sse_buf.push('\n');
        for event in drain_sse_events(&mut sse_buf) {
            if matches!(event, SseDataEvent::Done { .. } | SseDataEvent::Error(_)) {
                completed = true;
            }
            emit_sse(app, request_id, event);
        }
    }
    if !completed {
        return Err("The engine closed the reply before it finished.".to_string());
    }
    Ok(())
}

fn emit_sse(app: &AppHandle, request_id: &str, event: SseDataEvent) {
    match event {
        SseDataEvent::Delta(delta) => emit_stream(
            app,
            EngineStreamEvent {
                request_id: request_id.to_string(),
                delta: Some(delta),
                done: false,
                error: None,
                content: None,
                citations: None,
                goal_refs: None,
                tool: None,
                goal: None,
            },
        ),
        SseDataEvent::Tool(tool) => emit_stream(
            app,
            EngineStreamEvent {
                request_id: request_id.to_string(),
                delta: None,
                done: false,
                error: None,
                content: None,
                citations: None,
                goal_refs: None,
                tool: Some(tool),
                goal: None,
            },
        ),
        SseDataEvent::Goal(goal) => emit_stream(
            app,
            EngineStreamEvent {
                request_id: request_id.to_string(),
                delta: None,
                done: false,
                error: None,
                content: None,
                citations: None,
                goal_refs: None,
                tool: None,
                goal: Some(goal),
            },
        ),
        SseDataEvent::Error(message) => emit_stream(
            app,
            EngineStreamEvent {
                request_id: request_id.to_string(),
                delta: None,
                done: true,
                error: Some(message),
                content: None,
                citations: None,
                goal_refs: None,
                tool: None,
                goal: None,
            },
        ),
        SseDataEvent::Done {
            content,
            citations,
            goal_refs,
        } => emit_stream(
            app,
            EngineStreamEvent {
                request_id: request_id.to_string(),
                delta: None,
                done: true,
                error: None,
                content: Some(content),
                citations: Some(citations),
                goal_refs: Some(goal_refs),
                tool: None,
                goal: None,
            },
        ),
    }
}

fn emit_stream(app: &AppHandle, event: EngineStreamEvent) {
    let _ = app.emit(ENGINE_STREAM_EVENT, event);
}

type EngineHttpHead = (u16, Vec<(String, String)>, Vec<u8>);

fn read_http_head(
    stream: &mut TcpStream,
    cancelled: &impl Fn() -> bool,
) -> Result<EngineHttpHead, String> {
    let mut acc = Vec::new();
    let mut buf = [0u8; 2048];
    let started = Instant::now();
    loop {
        if cancelled() {
            return Err("cancelled".to_string());
        }
        if started.elapsed() > STREAM_MAX_IDLE {
            return Err("timed out reading response headers".to_string());
        }
        match stream.read(&mut buf) {
            Ok(0) => return Err("engine closed the stream".to_string()),
            Ok(n) => {
                acc.extend_from_slice(&buf[..n]);
                if let Some(pos) = find_header_end(&acc) {
                    let header_text = String::from_utf8_lossy(&acc[..pos]);
                    let leftover = acc[pos..].to_vec();
                    let (status, headers) = parse_response_headers(&header_text)?;
                    return Ok((status, headers, leftover));
                }
            }
            Err(error) if matches!(error.kind(), ErrorKind::TimedOut | ErrorKind::WouldBlock) => {
                continue;
            }
            Err(error) => return Err(error.to_string()),
        }
    }
}

fn read_remaining_body(
    stream: &mut TcpStream,
    leftover: Vec<u8>,
    chunked: bool,
    cancelled: &impl Fn() -> bool,
) -> Result<String, String> {
    let mut decoder = if chunked {
        Some(ChunkDecoder::default())
    } else {
        None
    };
    let mut body = Vec::new();
    let mut push = |bytes: &[u8]| -> Result<(), String> {
        if let Some(decoder) = decoder.as_mut() {
            body.extend(decoder.push(bytes)?);
        } else {
            body.extend_from_slice(bytes);
        }
        Ok(())
    };
    if !leftover.is_empty() {
        push(&leftover)?;
    }
    let mut buf = [0u8; 4096];
    let mut last_data = Instant::now();
    loop {
        if cancelled() {
            return Err("cancelled".to_string());
        }
        if last_data.elapsed() > STREAM_MAX_IDLE {
            break;
        }
        match stream.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                last_data = Instant::now();
                push(&buf[..n])?;
            }
            Err(error) if matches!(error.kind(), ErrorKind::TimedOut | ErrorKind::WouldBlock) => {
                continue;
            }
            Err(error) => return Err(error.to_string()),
        }
    }
    Ok(String::from_utf8_lossy(&body).into_owned())
}

fn find_header_end(acc: &[u8]) -> Option<usize> {
    acc.windows(4)
        .position(|window| window == b"\r\n\r\n")
        .map(|index| index + 4)
        .or_else(|| {
            acc.windows(2)
                .position(|window| window == b"\n\n")
                .map(|index| index + 2)
        })
}

fn parse_response_headers(header_text: &str) -> Result<(u16, Vec<(String, String)>), String> {
    let mut lines = header_text.lines();
    let status_line = lines.next().unwrap_or("");
    let status: u16 = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|item| item.parse().ok())
        .ok_or_else(|| "engine stream response had no status".to_string())?;
    let mut headers = Vec::new();
    for line in lines {
        if let Some((name, value)) = line.split_once(':') {
            headers.push((name.trim().to_string(), value.trim().to_string()));
        }
    }
    Ok((status, headers))
}

fn detail_from_body(status: u16, body: &str) -> String {
    if let Ok(value) = serde_json::from_str::<serde_json::Value>(body) {
        if let Some(detail) = value.get("detail").and_then(|item| item.as_str()) {
            return detail.to_string();
        }
    }
    let trimmed = body.trim();
    if trimmed.is_empty() {
        format!("engine request failed: {status}")
    } else {
        trimmed.to_string()
    }
}

fn parse_sse_data_line(line: &str) -> Option<SseDataEvent> {
    let trimmed = line.trim_end_matches(['\r', '\n']);
    let data = trimmed.strip_prefix("data:")?.trim();
    if data.is_empty() || data == "[DONE]" {
        return None;
    }
    let value: serde_json::Value = serde_json::from_str(data).ok()?;
    if let Some(tool) = value.get("tool") {
        return Some(SseDataEvent::Tool(tool.clone()));
    }
    if let Some(goal) = value.get("goal") {
        return Some(SseDataEvent::Goal(goal.clone()));
    }
    if let Some(error) = value.get("error") {
        return Some(SseDataEvent::Error(
            error
                .as_str()
                .unwrap_or("engine stream error")
                .to_string(),
        ));
    }
    let done = value.get("done").and_then(|item| item.as_bool()) == Some(true);
    if done || (value.get("content").is_some() && value.get("citations").is_some()) {
        return Some(SseDataEvent::Done {
            content: value
                .get("content")
                .and_then(|item| item.as_str())
                .unwrap_or("")
                .to_string(),
            citations: parse_stream_citations(&value),
            goal_refs: parse_goal_refs(&value),
        });
    }
    value
        .get("delta")
        .and_then(|item| item.as_str())
        .map(|delta| SseDataEvent::Delta(delta.to_string()))
}

fn drain_sse_events(buffer: &mut String) -> Vec<SseDataEvent> {
    let mut events = Vec::new();
    while let Some(index) = buffer.find('\n') {
        let line: String = buffer.drain(..=index).collect();
        if let Some(event) = parse_sse_data_line(&line) {
            events.push(event);
        }
    }
    events
}

fn parse_stream_citations(value: &serde_json::Value) -> Vec<StreamCitation> {
    value
        .get("citations")
        .and_then(|item| item.as_array())
        .into_iter()
        .flatten()
        .filter_map(|item| {
            let path = item.get("path").and_then(|value| value.as_str())?.to_string();
            let start = item
                .get("start_line")
                .or_else(|| item.get("startLine"))
                .and_then(|value| value.as_u64())
                .unwrap_or(0) as u32;
            let end = item
                .get("end_line")
                .or_else(|| item.get("endLine"))
                .and_then(|value| value.as_u64())
                .map(|value| value as u32);
            Some(StreamCitation {
                path,
                start_line: start,
                end_line: end,
            })
        })
        .collect()
}

fn parse_goal_refs(value: &serde_json::Value) -> Vec<String> {
    value
        .get("goal_refs")
        .or_else(|| value.get("goalRefs"))
        .and_then(|item| item.as_array())
        .into_iter()
        .flatten()
        .filter_map(|item| item.as_str().map(str::to_string))
        .collect()
}

#[derive(Default)]
struct ChunkDecoder {
    buf: Vec<u8>,
    finished: bool,
}

impl ChunkDecoder {
    fn push(&mut self, data: &[u8]) -> Result<Vec<u8>, String> {
        if self.finished {
            return Ok(Vec::new());
        }
        self.buf.extend_from_slice(data);
        let mut out = Vec::new();
        while let Some(pos) = self.buf.windows(2).position(|window| window == b"\r\n") {
            let size_line = std::str::from_utf8(&self.buf[..pos]).map_err(|error| error.to_string())?;
            let size = usize::from_str_radix(size_line.trim(), 16)
                .map_err(|_| "invalid chunk size".to_string())?;
            let header_end = pos + 2;
            if size == 0 {
                self.finished = true;
                self.buf.clear();
                break;
            }
            let chunk_end = header_end + size + 2;
            if self.buf.len() < chunk_end {
                break;
            }
            out.extend_from_slice(&self.buf[header_end..header_end + size]);
            self.buf.drain(..chunk_end);
        }
        Ok(out)
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
    if path == "/models/embeddings/install" || path == "/models/embeddings/install/" {
        return method == "GET" || method == "POST" || method == "DELETE";
    }
    if let Some(rest) = path.strip_prefix("/models/profiles/") {
        return method == "PUT" && skill_memory_id_ok(rest);
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
    if path == "/conversations" || path == "/conversations/" {
        return method == "GET" || method == "POST";
    }
    if let Some(rest) = path.strip_prefix("/conversations/") {
        let rest = rest.trim_end_matches('/');
        if rest.is_empty() {
            return false;
        }
        if let Some((id, action)) = rest.split_once('/') {
            let action = action.trim_end_matches('/');
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
        return (method == "GET" || method == "DELETE") && skill_memory_id_ok(rest);
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
                    | ("GET", Some("conversations"))
                    | ("GET", Some("safety"))
                    | ("GET", Some("files"))
                    | ("GET", Some("files/contents"))
                    | ("PUT", Some("files/contents"))
                    | ("GET", Some("changes"))
                    | ("GET", Some("goal-readiness"))
                    | ("POST", Some("conversations"))
                    | ("POST", Some("autonomy"))
                    | ("POST", Some("index/rebuild"))
                    | ("POST", Some("index/refresh"))
                    | ("POST", Some("index/watch"))
                    | ("POST", Some("commits"))
                    | ("POST", Some("writes/revert"))
                    | ("GET", Some("terminal/runs"))
                    | ("POST", Some("terminal/runs"))
                    | ("POST", Some("terminal/runs/cancel"))
                    | ("POST", Some("terminal/sessions"))
                    | ("POST", Some("terminal/sessions/input"))
                    | ("POST", Some("terminal/sessions/size"))
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
    let (program, args) = engine_command(app)?;
    let log_path = paths.logs.join("engine.log");
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|error| error.to_string())?;

    let mut command = Command::new(&program);
    if args.is_empty() {
        if let Some(parent) = program.parent() {
            if !parent.as_os_str().is_empty() {
                command.current_dir(parent);
            }
        }
    }
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

fn engine_sidecar_name() -> &'static str {
    if cfg!(windows) {
        "kronos-engine.exe"
    } else {
        "kronos-engine"
    }
}

fn resolve_bundled_engine_executable(candidate: &Path) -> Option<PathBuf> {
    if candidate.is_file() {
        return Some(candidate.to_path_buf());
    }
    if candidate.is_dir() {
        let nested = candidate.join(engine_sidecar_name());
        if nested.is_file() {
            return Some(nested);
        }
    }
    None
}

fn resolve_engine_command(
    env_bin: Option<&str>,
    resource_dir: Option<&Path>,
    current_exe_dir: Option<&Path>,
) -> Result<(PathBuf, Vec<String>), String> {
    if let Some(bin) = env_bin {
        let path = PathBuf::from(bin);
        if let Some(resolved) = resolve_bundled_engine_executable(&path) {
            return Ok((resolved, Vec::new()));
        }
        return Err(format!(
            "KRONOS_ENGINE_BIN does not exist: {}",
            path.display()
        ));
    }

    if let Some(resource_dir) = resource_dir {
        let mut resource_candidates = vec![resource_dir.join("engine").join(engine_sidecar_name())];
        if cfg!(windows) {
            resource_candidates.push(resource_dir.join("engine").join("kronos-engine"));
        }
        for candidate in resource_candidates {
            if let Some(resolved) = resolve_bundled_engine_executable(&candidate) {
                return Ok((resolved, Vec::new()));
            }
        }
    }

    if let Some(dir) = current_exe_dir {
        for name in ["kronos-engine.exe", "kronos-engine"] {
            let candidate = dir.join(name);
            if let Some(resolved) = resolve_bundled_engine_executable(&candidate) {
                return Ok((resolved, Vec::new()));
            }
        }
    }

    let python = python_executable();
    Ok((
        PathBuf::from(python),
        vec!["-m".to_string(), "kronos_engine".to_string()],
    ))
}

fn engine_command(app: &AppHandle) -> Result<(PathBuf, Vec<String>), String> {
    let env_bin = std::env::var("KRONOS_ENGINE_BIN").ok();
    let resource_dir = app.path().resource_dir().ok();
    let current_exe_dir = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(Path::to_path_buf));
    resolve_engine_command(
        env_bin.as_deref(),
        resource_dir.as_deref(),
        current_exe_dir.as_deref(),
    )
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
    if method == "POST"
        && (normalized.ends_with("/index/rebuild") || normalized.ends_with("/index/refresh"))
    {
        return INDEX_JOB_TIMEOUT;
    }
    if method == "POST" && normalized.ends_with("/terminal/runs") {
        return TERMINAL_RUN_TIMEOUT;
    }
    if method == "POST" || method == "PUT" {
        return ENGINE_JSON_TIMEOUT;
    }
    ENGINE_JSON_GET_TIMEOUT
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
    use std::path::PathBuf;

    #[test]
    fn allowlist_includes_models_and_repositories() {
        assert!(engine_path_allowed("GET", "/models"));
        assert!(engine_path_allowed("POST", "/models/providers"));
        assert!(engine_path_allowed("PUT", "/models/assignments"));
        assert!(engine_path_allowed("GET", "/models/embeddings/install"));
        assert!(engine_path_allowed("POST", "/models/embeddings/install"));
        assert!(engine_path_allowed("DELETE", "/models/embeddings/install?key=minilm-l6-v2"));
        assert!(!engine_path_allowed("GET", "/models/embeddings/install/extra"));
        assert!(!engine_path_allowed("DELETE", "/models/embeddings/install/../secret"));
        assert!(engine_path_allowed("PUT", "/models/profiles/prof_prov_abc_coder"));
        assert!(!engine_path_allowed("GET", "/models/profiles/prof_prov_abc_coder"));
        assert!(!engine_path_allowed("PUT", "/models/profiles/../secret"));
        assert!(!engine_path_allowed("GET", "/models/assignments"));
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
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/index/watch"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/index/map"));
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
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/safety"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/autonomy"));
        assert!(!engine_path_allowed("DELETE", "/repositories/repo_alpha/safety"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/conversations"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/conversations"));
        assert!(engine_path_allowed("GET", "/conversations/conv_abc"));
        assert!(engine_path_allowed("POST", "/conversations/conv_abc/messages"));
        assert!(engine_path_allowed("DELETE", "/conversations/conv_abc"));
        assert!(!engine_path_allowed("GET", "/conversations/conv_abc/messages"));
        assert!(!engine_path_allowed("DELETE", "/repositories/repo_alpha/conversations"));
        assert!(!engine_path_allowed("POST", "/conversations/../secret/messages"));
    }

    #[test]
    fn allowlist_includes_conversation_collection_and_workspace_routes() {
        assert!(engine_path_allowed("GET", "/conversations"));
        assert!(engine_path_allowed("POST", "/conversations"));
        assert!(engine_path_allowed("GET", "/conversations/"));
        assert!(engine_path_allowed("POST", "/conversations/"));
        assert!(engine_path_allowed("POST", "/conversations/conv_abc/cancel"));
        assert!(engine_path_allowed("GET", "/conversations/conv_abc/images/img_abc"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/files"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/files/contents"));
        assert!(engine_path_allowed(
            "GET",
            "/repositories/repo_alpha/files/contents?path=src%2Fapp.py"
        ));
        assert!(engine_path_allowed("PUT", "/repositories/repo_alpha/files/contents"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/changes"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/commits"));
        assert!(engine_path_allowed("POST", "/repositories/repo_alpha/writes/revert"));
        assert!(engine_path_allowed("GET", "/repositories/repo_alpha/goal-readiness"));
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
        assert!(engine_path_allowed(
            "POST",
            "/repositories/repo_alpha/terminal/sessions/size"
        ));
        assert!(!engine_path_allowed("GET", "/chat/sessions"));
        assert!(!engine_path_allowed("POST", "/chat/sessions"));
        assert!(!engine_path_allowed("POST", "/chat/sessions/chat_1/messages"));
        assert!(!engine_path_allowed(
            "GET",
            "/conversations/conv_abc/images/../secret"
        ));
        assert!(!engine_path_allowed(
            "GET",
            "/conversations/conv_abc/images/img_abc/extra"
        ));
        assert!(!engine_path_allowed(
            "POST",
            "/conversations/conv_abc/images/img_abc"
        ));
    }

    #[test]
    fn engine_stream_command_returns_result_for_tauri_state_refs() {
        let src = include_str!("engine.rs");
        let start = src
            .find("pub async fn engine_stream(")
            .expect("engine_stream command");
        let signature = &src[start..start.saturating_add(500)];
        assert!(
            signature.contains("-> Result<(), String>"),
            "Tauri 2 rejects async commands with State<'_> unless they return Result"
        );
    }

    #[test]
    fn stream_cancel_flag_is_visible_to_a_worker_thread() {
        let cancels = super::StreamCancels::default();
        let worker = cancels.clone();
        let (started_tx, started_rx) = std::sync::mpsc::channel();
        let handle = std::thread::spawn(move || {
            started_tx.send(()).unwrap();
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
            while std::time::Instant::now() < deadline {
                if worker.is_cancelled("req-1") {
                    return true;
                }
                std::thread::sleep(std::time::Duration::from_millis(1));
            }
            false
        });
        started_rx.recv().unwrap();
        cancels.cancel("req-1");
        assert!(handle.join().unwrap());
        cancels.finish("req-1");
        assert!(!cancels.is_cancelled("req-1"));
    }

    #[test]
    fn parse_sse_delta_and_done_lines() {
        assert_eq!(
            super::parse_sse_data_line(r#"data: {"delta": "Hel"}"#),
            Some(super::SseDataEvent::Delta("Hel".into()))
        );
        assert_eq!(
            super::parse_sse_data_line(
                r#"data: {"content":"Hello","citations":[{"path":"a.py","start_line":3,"end_line":5}],"goal_refs":["goal_1"],"done": true}"#
            ),
            Some(super::SseDataEvent::Done {
                content: "Hello".into(),
                citations: vec![super::StreamCitation {
                    path: "a.py".into(),
                    start_line: 3,
                    end_line: Some(5),
                }],
                goal_refs: vec!["goal_1".into()],
            })
        );
        assert_eq!(super::parse_sse_data_line("event: message"), None);
        assert_eq!(super::parse_sse_data_line("data: [DONE]"), None);
    }

    #[test]
    fn parse_sse_forwards_tool_goal_and_error() {
        assert_eq!(
            super::parse_sse_data_line(
                r#"data: {"tool": {"id": "t1", "name": "read_file", "status": "running", "args": {"path": "a.py"}}}"#
            ),
            Some(super::SseDataEvent::Tool(serde_json::json!({
                "id": "t1",
                "name": "read_file",
                "status": "running",
                "args": {"path": "a.py"}
            })))
        );
        assert_eq!(
            super::parse_sse_data_line(
                r#"data: {"goal": {"id": "goal_x", "state": "draft", "can_execute": false, "readiness": []}}"#
            ),
            Some(super::SseDataEvent::Goal(serde_json::json!({
                "id": "goal_x",
                "state": "draft",
                "can_execute": false,
                "readiness": []
            })))
        );
        assert_eq!(
            super::parse_sse_data_line(r#"data: {"error": "the model did not answer"}"#),
            Some(super::SseDataEvent::Error("the model did not answer".into()))
        );
        assert_eq!(
            super::parse_sse_data_line(r#"data: {"error": "failed", "done": true}"#),
            Some(super::SseDataEvent::Error("failed".into()))
        );
    }

    #[test]
    fn drain_sse_keeps_incomplete_line() {
        let mut buf = String::from("data: {\"delta\": \"a\"}\n\ndata: {\"delta\": \"b");
        let events = super::drain_sse_events(&mut buf);
        assert_eq!(events, vec![super::SseDataEvent::Delta("a".into())]);
        assert!(buf.contains('b'));
    }

    #[test]
    fn drain_sse_flushes_incomplete_line_after_newline() {
        let mut buf = String::from(r#"data: {"delta": "tail"}"#);
        buf.push('\n');
        let events = super::drain_sse_events(&mut buf);
        assert_eq!(events, vec![super::SseDataEvent::Delta("tail".into())]);
        assert!(buf.is_empty());
    }

    #[test]
    fn stream_event_json_omits_secrets_and_uses_camel_case() {
        let payload = super::EngineStreamEvent {
            request_id: "r1".into(),
            delta: Some("x".into()),
            done: false,
            error: None,
            content: None,
            citations: None,
            goal_refs: None,
            tool: None,
            goal: None,
        };
        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("requestId"));
        assert!(!json.to_lowercase().contains("bearer"));
        assert!(!json.contains("http://"));
        assert!(!json.contains("Authorization"));
    }

    #[test]
    fn chunk_decoder_yields_payload() {
        let mut decoder = super::ChunkDecoder::default();
        let decoded = decoder
            .push(b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n")
            .unwrap();
        assert_eq!(decoded, b"hello world");
    }

    #[test]
    fn chunk_decoder_waits_for_incomplete_chunk() {
        let mut decoder = super::ChunkDecoder::default();
        assert_eq!(decoder.push(b"5\r\nhel").unwrap(), b"");
        assert_eq!(decoder.push(b"lo\r\n0\r\n\r\n").unwrap(), b"hello");
    }

    #[test]
    fn engine_json_timeout_table() {
        use super::{engine_json_timeout, PROBE_TIMEOUT};
        use std::time::Duration;

        assert_eq!(PROBE_TIMEOUT, Duration::from_secs(2));
        assert_eq!(
            engine_json_timeout("POST", "/repositories/repo_alpha/index/rebuild"),
            Duration::from_secs(180)
        );
        assert_eq!(
            engine_json_timeout("POST", "/repositories/repo_alpha/index/refresh"),
            Duration::from_secs(180)
        );
        assert_eq!(
            engine_json_timeout("POST", "/conversations"),
            Duration::from_secs(30)
        );
        assert_eq!(
            engine_json_timeout("PUT", "/repositories/repo_alpha/files/contents"),
            Duration::from_secs(30)
        );
        assert_eq!(
            engine_json_timeout("GET", "/ops/doctor"),
            Duration::from_secs(8)
        );
        assert_eq!(
            engine_json_timeout("GET", "/repositories/repo_alpha/files"),
            Duration::from_secs(8)
        );
        assert_eq!(
            engine_json_timeout("POST", "/conversations/conv_abc/messages"),
            Duration::from_secs(30)
        );
        assert_eq!(
            engine_json_timeout("POST", "/repositories/repo_alpha/terminal/runs"),
            Duration::from_secs(90)
        );
        assert_eq!(
            engine_json_timeout("GET", "/repositories/repo_alpha/terminal/runs"),
            Duration::from_secs(8)
        );
        let src = include_str!("engine.rs");
        assert!(
            src.contains("loopback_request(\"GET\", url, extra_headers, None, PROBE_TIMEOUT)"),
            "loopback_get / ready-check must keep the 2s probe timeout"
        );
    }

    #[test]
    fn engine_command_prefers_env_bin_over_resource_and_sibling() {
        let temp = tempfile::tempdir().unwrap();
        let env_bin = temp.path().join("custom-engine");
        std::fs::write(&env_bin, "bin").unwrap();
        let resource_dir = temp.path().join("resources");
        let resource_engine = resource_dir.join("engine").join("kronos-engine");
        std::fs::create_dir_all(resource_engine.parent().unwrap()).unwrap();
        std::fs::write(&resource_engine, "resource").unwrap();
        let sibling_dir = temp.path().join("app");
        std::fs::create_dir_all(&sibling_dir).unwrap();
        std::fs::write(sibling_dir.join("kronos-engine"), "sibling").unwrap();

        let resolved = super::resolve_engine_command(
            Some(env_bin.to_str().unwrap()),
            Some(&resource_dir),
            Some(&sibling_dir),
        )
        .unwrap();
        assert_eq!(resolved.0, env_bin);
        assert!(resolved.1.is_empty());
    }

    #[test]
    fn engine_command_uses_resource_dir_before_sibling_and_python() {
        let temp = tempfile::tempdir().unwrap();
        let resource_dir = temp.path().join("resources");
        let resource_engine = resource_dir.join("engine").join("kronos-engine");
        std::fs::create_dir_all(resource_engine.parent().unwrap()).unwrap();
        std::fs::write(&resource_engine, "resource").unwrap();
        let sibling_dir = temp.path().join("app");
        std::fs::create_dir_all(&sibling_dir).unwrap();
        std::fs::write(sibling_dir.join("kronos-engine"), "sibling").unwrap();

        let resolved = super::resolve_engine_command(None, Some(&resource_dir), Some(&sibling_dir))
            .unwrap();
        assert_eq!(resolved.0, resource_engine);
        assert!(resolved.1.is_empty());
    }

    #[test]
    fn engine_command_uses_sibling_before_python_fallback() {
        let temp = tempfile::tempdir().unwrap();
        let sibling_dir = temp.path().join("app");
        std::fs::create_dir_all(&sibling_dir).unwrap();
        let sibling_engine = sibling_dir.join("kronos-engine");
        std::fs::write(&sibling_engine, "sibling").unwrap();

        let resolved = super::resolve_engine_command(None, None, Some(&sibling_dir)).unwrap();
        assert_eq!(resolved.0, sibling_engine);
        assert!(resolved.1.is_empty());
    }

    #[test]
    fn engine_command_falls_back_to_python_module() {
        let resolved = super::resolve_engine_command(None, None, None).unwrap();
        let expected_python = if cfg!(windows) { "python" } else { "python3" };
        assert_eq!(resolved.0, PathBuf::from(expected_python));
        assert_eq!(
            resolved.1,
            vec!["-m".to_string(), "kronos_engine".to_string()]
        );
    }

    #[test]
    fn engine_command_resolves_onedir_folder_under_resources() {
        let temp = tempfile::tempdir().unwrap();
        let resource_dir = temp.path().join("resources");
        let onedir = resource_dir.join("engine").join("kronos-engine");
        let nested = onedir.join("kronos-engine");
        std::fs::create_dir_all(&onedir).unwrap();
        std::fs::write(&nested, "onedir").unwrap();

        let resolved = super::resolve_engine_command(None, Some(&resource_dir), None).unwrap();
        assert_eq!(resolved.0, nested);
        assert!(resolved.1.is_empty());
    }
}
