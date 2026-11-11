use crate::contract::{EngineHealth, ErrorCode, ProcessorTask, TaskEvent};
use serde_json::Value;
use std::{
    collections::{HashMap, HashSet},
    io::{self, BufRead, BufReader, Write},
    path::PathBuf,
    process::{Command, Stdio},
    sync::{mpsc::{self, Sender}, Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager};
use uuid::Uuid;

const MAX_STDOUT_FRAME: usize = 64 * 1024 * 1024;
const MAX_STDERR_FRAME: usize = 1024 * 1024;

struct LimitedLine {
    bytes: Vec<u8>,
    truncated: bool,
    eof: bool,
}

/// Reads one newline-delimited frame without allowing an unterminated line to grow forever.
/// When the cap is exceeded, the remainder of that frame is consumed through its newline so
/// the next call starts at the next frame.
fn read_limited_line<R: BufRead>(reader: &mut R, max_bytes: usize) -> io::Result<LimitedLine> {
    let cap = max_bytes.max(1);
    let mut bytes = Vec::with_capacity(cap.min(8192));
    let mut consumed_any = false;
    let mut truncated = false;

    loop {
        let (consumed, ended) = {
            let chunk = reader.fill_buf()?;
            if chunk.is_empty() {
                return Ok(LimitedLine { bytes, truncated, eof: !consumed_any });
            }
            consumed_any = true;

            if let Some(newline) = chunk.iter().position(|byte| *byte == b'\n') {
                let frame_len = newline + 1;
                if bytes.len() < cap {
                    let keep = (cap - bytes.len()).min(frame_len);
                    bytes.extend_from_slice(&chunk[..keep]);
                    truncated |= keep < frame_len;
                } else {
                    truncated = true;
                }
                (frame_len, true)
            } else {
                let chunk_len = chunk.len();
                if bytes.len() < cap {
                    let keep = (cap - bytes.len()).min(chunk_len);
                    bytes.extend_from_slice(&chunk[..keep]);
                    truncated |= keep < chunk_len;
                } else {
                    truncated = true;
                }
                (chunk_len, false)
            }
        };
        reader.consume(consumed);
        if ended {
            return Ok(LimitedLine { bytes, truncated, eof: false });
        }
    }
}

struct Inner {
    // Spawning is performed while this mutex is held. That makes the sender and generation
    // transition atomic with respect to all callers of ensure_running.
    sender: Option<Sender<String>>,
    generation: u64,
    in_flight: Arc<Mutex<HashSet<String>>>,
    pending: HashMap<String, Sender<Result<Value, Value>>>,
    health: EngineHealth,
    crash_count: u32,
    restart_not_before: Option<Instant>,
    started_at: Option<Instant>,
}

#[derive(Clone)]
pub struct SidecarManager {
    inner: Arc<Mutex<Inner>>,
}

fn restart_delay(crash_count: u32) -> Duration {
    let multiplier = 1_u64 << crash_count.min(6);
    Duration::from_millis((500_u64.saturating_mul(multiplier)).min(30_000))
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(Inner {
                sender: None,
                generation: 0,
                in_flight: Arc::new(Mutex::new(HashSet::new())),
                pending: HashMap::new(),
                health: EngineHealth::default(),
                crash_count: 0,
                restart_not_before: None,
                started_at: None,
            })),
        }
    }

    fn command(app: &AppHandle) -> (Command, PathBuf) {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let repo = manifest
            .parent()
            .unwrap_or(&manifest)
            .parent()
            .unwrap_or(&manifest)
            .to_path_buf();
        let engine = repo.join("engine");
        let binary_name = if cfg!(windows) {
            "docforge-engine-x86_64-pc-windows-msvc.exe"
        } else {
            "docforge-engine-x86_64-unknown-linux-gnu"
        };
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|path| path.parent().map(PathBuf::from));
        let resource_dir = app.path().resource_dir().ok();
        let sidecar_candidates = [
            exe_dir.clone().map(|dir| dir.join("binaries").join(binary_name)),
            exe_dir.clone().map(|dir| dir.join("resources").join(binary_name)),
            resource_dir.clone().map(|dir| dir.join(binary_name)),
            resource_dir.clone().map(|dir| dir.join("docforge-engine.exe")),
            Some(manifest.join("binaries").join(binary_name)),
        ];
        let sidecar = sidecar_candidates.into_iter().flatten().find(|path| path.exists())
            .unwrap_or_else(|| manifest.join("binaries").join(binary_name));
        let dev = cfg!(debug_assertions) || std::env::var_os("DOCFORGE_ENGINE_DEV").is_some();
        if dev {
            let python = if cfg!(windows) {
                engine.join(".venv/Scripts/python.exe")
            } else {
                engine.join(".venv/bin/python")
            };
            let mut command = if python.exists() {
                Command::new(python)
            } else {
                Command::new(if cfg!(windows) { "python" } else { "python3" })
            };
            command.args(["-m", "docforge_engine", "serve"]);
            (command, engine)
        } else {
            (Command::new(sidecar), repo)
        }
    }

    fn ensure_running(&self, app: &AppHandle) -> Result<(), String> {
        let mut state = self.inner.lock().map_err(|error| error.to_string())?;
        if state.sender.is_some() {
            return Ok(());
        }
        if let Some(deadline) = state.restart_not_before {
            if deadline > Instant::now() {
                let remaining = deadline.saturating_duration_since(Instant::now()).as_millis();
                return Err(format!("El motor se reiniciara en {remaining} ms."));
            }
            state.restart_not_before = None;
        }

        let (mut command, cwd) = Self::command(app);
        command
            .current_dir(cwd)
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let mut child = command
            .spawn()
            .map_err(|error| format!("No se pudo iniciar el motor: {error}"))?;
        let stdin = child.stdin.take().ok_or_else(|| "El motor no expuso stdin".to_string())?;
        let stdout = child.stdout.take().ok_or_else(|| "El motor no expuso stdout".to_string())?;

        if let Some(stderr) = child.stderr.take() {
            thread::spawn(move || {
                let mut reader = BufReader::new(stderr);
                loop {
                    match read_limited_line(&mut reader, MAX_STDERR_FRAME) {
                        Ok(frame) if frame.eof => break,
                        Ok(frame) => {
                            let line = String::from_utf8_lossy(&frame.bytes);
                            if frame.truncated {
                                eprintln!("[docforge-engine] {} [linea stderr truncada]", line.trim_end());
                            } else {
                                eprintln!("[docforge-engine] {}", line.trim_end());
                            }
                        }
                        Err(error) => {
                            eprintln!("[docforge-engine] error leyendo stderr: {error}");
                            break;
                        }
                    }
                }
            });
        }

        let generation = state.generation + 1;
        let started_at = Instant::now();
        let (tx, rx) = mpsc::channel::<String>();
        let inner = self.inner.clone();
        let app_for_reader = app.clone();
        thread::spawn(move || {
            let mut input = stdin;
            for line in rx {
                if input
                    .write_all(line.as_bytes())
                    .and_then(|_| input.write_all(b"\n"))
                    .and_then(|_| input.flush())
                    .is_err()
                {
                    break;
                }
            }
        });

        let in_flight = state.in_flight.clone();
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let frame = match read_limited_line(&mut reader, MAX_STDOUT_FRAME) {
                    Ok(frame) if frame.eof => break,
                    Ok(frame) => frame,
                    Err(error) => {
                        eprintln!("[docforge-engine] error leyendo stdout: {error}");
                        break;
                    }
                };
                if frame.truncated {
                    eprintln!("[docforge-engine] linea stdout excedio 64 MiB; se descarta");
                    continue;
                }
                let line = match std::str::from_utf8(&frame.bytes) {
                    Ok(text) => text.trim().to_owned(),
                    Err(_) => {
                        eprintln!("[docforge-engine] linea no UTF-8 recibida; decodificando con reemplazo");
                        String::from_utf8_lossy(&frame.bytes).trim().to_owned()
                    }
                };
                if line.is_empty() {
                    continue;
                }
                let Ok(value) = serde_json::from_str::<Value>(&line) else {
                    eprintln!("[docforge-engine] stdout no-JSON ignorado: {line}");
                    continue;
                };
                if value.get("type").and_then(Value::as_str) == Some("health") {
                    if let Ok(health) = serde_json::from_value::<EngineHealth>(value.clone()) {
                        if let Ok(mut state) = inner.lock() {
                            state.health = health.clone();
                        }
                        let _ = app_for_reader.emit("engine://health", health);
                    }
                } else if value.get("type").and_then(Value::as_str) == Some("rpc_result") {
                    let rpc_id = value.get("rpcId").and_then(Value::as_str).map(str::to_owned);
                    if let Some(rpc_id) = rpc_id {
                        let result = if value.get("ok").and_then(Value::as_bool) == Some(true) {
                            Ok(value.get("result").cloned().unwrap_or(Value::Null))
                        } else {
                            // Preserve complete RPC errors, including CANCELLED/BUSY.
                            Err(value.get("error").cloned().unwrap_or_else(|| {
                                serde_json::json!({
                                    "code": "INTERNAL",
                                    "message": "El motor devolvio un error RPC sin detalles."
                                })
                            }))
                        };
                        if let Ok(mut state) = inner.lock() {
                            if let Some(waiter) = state.pending.remove(&rpc_id) {
                                let _ = waiter.send(result);
                            }
                        }
                    }
                } else {
                    let event = match serde_json::from_value::<TaskEvent>(value.clone()) {
                        Ok(event) => event,
                        Err(error) => {
                            eprintln!("[docforge-engine] evento fuera de contrato ({error}): {line}");
                            let Some(id) = value.get("id").and_then(Value::as_str).filter(|id| !id.is_empty()) else {
                                continue;
                            };
                            if value.get("type").and_then(Value::as_str) != Some("error") {
                                continue;
                            }
                            TaskEvent::Error {
                                id: id.to_string(),
                                code: ErrorCode::Internal,
                                message: value
                                    .get("message")
                                    .and_then(Value::as_str)
                                    .unwrap_or("El motor devolvio un error no reconocido.")
                                    .to_string(),
                                details: value.get("details").map(|details| match details {
                                    Value::String(text) => text.clone(),
                                    other => other.to_string(),
                                }),
                            }
                        }
                    };
                    let id = match &event {
                        TaskEvent::Progress { id, .. }
                        | TaskEvent::Log { id, .. }
                        | TaskEvent::Result { id, .. }
                        | TaskEvent::Error { id, .. } => id.clone(),
                    };
                    if matches!(&event, TaskEvent::Result { .. } | TaskEvent::Error { .. }) {
                        if let Ok(mut ids) = in_flight.lock() {
                            ids.remove(&id);
                        }
                    }
                    let _ = app_for_reader.emit("task://event", event);
                }
            }
        });

        let manager = self.clone();
        let app_for_wait = app.clone();
        thread::spawn(move || {
            let _ = child.wait();
            let (delay, pending, ids) = {
                let Ok(mut state) = manager.inner.lock() else { return };
                // An older process must never clear or fail a newer generation.
                if state.generation != generation || state.sender.is_none() {
                    return;
                }
                state.sender = None;
                if state.started_at.map(|started| started.elapsed() > Duration::from_secs(60)).unwrap_or(false) {
                    state.crash_count = 0;
                }
                let delay = restart_delay(state.crash_count);
                state.crash_count = state.crash_count.saturating_add(1);
                state.restart_not_before = Some(Instant::now() + delay);
                state.started_at = None;
                let pending = std::mem::take(&mut state.pending);
                let ids = state.in_flight.clone();
                (delay, pending, ids)
            };

            let error = serde_json::json!({
                "code": "INTERNAL",
                "message": "El sidecar se detuvo antes de responder."
            });
            for waiter in pending.into_values() {
                let _ = waiter.send(Err(error.clone()));
            }
            let pending_ids: Vec<String> = ids
                .lock()
                .map(|mut set| {
                    let list = set.iter().cloned().collect();
                    set.clear();
                    list
                })
                .unwrap_or_default();
            for id in pending_ids {
                let _ = app_for_wait.emit(
                    "task://event",
                    TaskEvent::Error {
                        id,
                        code: ErrorCode::Internal,
                        message: "El sidecar se detuvo; la tarea no termino.".into(),
                        details: None,
                    },
                );
            }

            thread::sleep(delay);
            let should_restart = manager
                .inner
                .lock()
                .map(|state| state.generation == generation && state.sender.is_none())
                .unwrap_or(false);
            if should_restart {
                let _ = manager.ensure_running(&app_for_wait);
            }
        });

        state.generation = generation;
        state.started_at = Some(started_at);
        state.sender = Some(tx);
        Ok(())
    }

    pub fn send_task(&self, app: &AppHandle, task: &ProcessorTask) -> Result<(), String> {
        self.ensure_running(app)?;
        let json = serde_json::to_string(task).map_err(|error| error.to_string())?;
        let state = self.inner.lock().map_err(|error| error.to_string())?;
        state.in_flight.lock().map_err(|error| error.to_string())?.insert(task.id.clone());
        state.sender.as_ref().ok_or_else(|| "El motor no esta disponible".to_string())?
            .send(json)
            .map_err(|error| error.to_string())
    }

    pub fn cancel(&self, app: &AppHandle, id: &str) -> Result<(), String> {
        self.ensure_running(app)?;
        let message = serde_json::json!({ "type": "cancel", "id": id }).to_string();
        self.inner
            .lock()
            .map_err(|error| error.to_string())?
            .sender
            .as_ref()
            .ok_or_else(|| "El motor no esta disponible".to_string())?
            .send(message)
            .map_err(|error| error.to_string())
    }

    pub fn rpc(
        &self,
        app: &AppHandle,
        method: String,
        params: Value,
        timeout: Duration,
    ) -> Result<Value, Value> {
        self.ensure_running(app)
            .map_err(|message| serde_json::json!({ "code": "INTERNAL", "message": message }))?;

        let rpc_id = Uuid::new_v4().to_string();
        let (tx, rx) = mpsc::channel::<Result<Value, Value>>();
        let message = serde_json::json!({
            "type": "rpc",
            "rpcId": rpc_id,
            "method": method,
            "params": params
        }).to_string();

        let sender = {
            let mut state = self.inner.lock().map_err(|error| serde_json::json!({ "code": "INTERNAL", "message": error.to_string() }))?;
            state.pending.insert(rpc_id.clone(), tx);
            state.sender.clone().ok_or_else(|| {
                state.pending.remove(&rpc_id);
                serde_json::json!({ "code": "INTERNAL", "message": "El motor no esta disponible." })
            })?
        };

        if sender.send(message).is_err() {
            if let Ok(mut state) = self.inner.lock() {
                state.pending.remove(&rpc_id);
            }
            return Err(serde_json::json!({ "code": "INTERNAL", "message": "No se pudo enviar la consulta al motor." }));
        }

        match rx.recv_timeout(timeout) {
            Ok(result) => result,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if let Ok(mut state) = self.inner.lock() {
                    state.pending.remove(&rpc_id);
                }
                let cancel = serde_json::json!({ "type": "rpc_cancel", "rpcId": rpc_id }).to_string();
                let _ = sender.send(cancel);
                Err(serde_json::json!({
                    "code": "TIMEOUT",
                    "message": "El motor tardo demasiado en responder a la consulta."
                }))
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => Err(serde_json::json!({
                "code": "INTERNAL",
                "message": "El canal RPC se cerro inesperadamente."
            })),
        }
    }

    pub fn health(&self, app: &AppHandle) -> Result<EngineHealth, String> {
        self.ensure_running(app)?;
        self.inner
            .lock()
            .map_err(|error| error.to_string())?
            .sender
            .as_ref()
            .ok_or_else(|| "El motor no esta disponible".to_string())?
            .send(serde_json::json!({ "type": "health" }).to_string())
            .map_err(|error| error.to_string())?;
        Ok(self.inner.lock().map_err(|error| error.to_string())?.health.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::read_limited_line;
    use std::io::Cursor;

    #[test]
    fn reads_a_normal_line() {
        let mut reader = Cursor::new(b"hello\nnext\n");
        let frame = read_limited_line(&mut reader, 64).expect("frame");
        assert_eq!(frame.bytes, b"hello\n");
        assert!(!frame.truncated);
        assert!(!frame.eof);
    }

    #[test]
    fn discards_the_rest_of_an_oversized_line() {
        let mut reader = Cursor::new(b"abcdef\nnext\n");
        let frame = read_limited_line(&mut reader, 3).expect("frame");
        assert_eq!(frame.bytes, b"abc");
        assert!(frame.truncated);
        let next = read_limited_line(&mut reader, 64).expect("next frame");
        assert_eq!(next.bytes, b"next\n");
        assert!(!next.truncated);
    }

    #[test]
    fn returns_a_partial_final_line() {
        let mut reader = Cursor::new(b"partial");
        let frame = read_limited_line(&mut reader, 64).expect("frame");
        assert_eq!(frame.bytes, b"partial");
        assert!(!frame.truncated);
        assert!(!frame.eof);
        assert!(read_limited_line(&mut reader, 64).expect("eof").eof);
    }
}
