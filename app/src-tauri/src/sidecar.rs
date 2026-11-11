use crate::contract::{EngineHealth, ErrorCode, ProcessorTask, TaskEvent};
use serde_json::Value;
use std::{
    collections::{HashMap, HashSet},
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Command, Stdio},
    sync::{
        mpsc::{self, Sender},
        Arc, Mutex,
    },
    thread,
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager};
use uuid::Uuid;

struct Inner {
    sender: Option<Sender<String>>,
    in_flight: Arc<Mutex<HashSet<String>>>,
    pending: HashMap<String, Sender<Result<Value, Value>>>,
    health: EngineHealth,
}
#[derive(Clone)]
pub struct SidecarManager {
    inner: Arc<Mutex<Inner>>,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(Inner {
                sender: None,
                in_flight: Arc::new(Mutex::new(HashSet::new())),
                pending: HashMap::new(),
                health: EngineHealth::default(),
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
        if self
            .inner
            .lock()
            .map_err(|e| e.to_string())?
            .sender
            .is_some()
        {
            return Ok(());
        }
        let (mut command, cwd) = Self::command(app);
        command
            .current_dir(cwd)
            // Windows pipes default to the ANSI code page (cp1252) in Python: force UTF-8 so
            // accented paths ("MAESTRÍA GESTIÓN") travel intact in both directions.
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let mut child = command
            .spawn()
            .map_err(|e| format!("No se pudo iniciar el motor: {e}"))?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "El motor no expuso stdin".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "El motor no expuso stdout".to_string())?;
        if let Some(stderr) = child.stderr.take() {
            thread::spawn(move || {
                let mut reader = BufReader::new(stderr);
                let mut buf = Vec::new();
                while matches!(reader.read_until(b'\n', &mut buf), Ok(n) if n > 0) {
                    let line = String::from_utf8_lossy(&buf);
                    eprintln!("[docforge-engine] {}", line.trim_end());
                    buf.clear();
                }
            });
        }
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
        let in_flight = inner.lock().map_err(|e| e.to_string())?.in_flight.clone();
        thread::spawn(move || {
            // Read raw bytes per line: `lines()` returns Err on invalid UTF-8 and `.flatten()`
            // silently dropped those events (progress/result) -> UI frozen at 0%.
            let mut reader = BufReader::new(stdout);
            let mut buf = Vec::new();
            loop {
                buf.clear();
                match reader.read_until(b'\n', &mut buf) {
                    Ok(0) => break,
                    Ok(_) => {}
                    Err(e) => {
                        eprintln!("[docforge-engine] error leyendo stdout: {e}");
                        break;
                    }
                }
                let line = match std::str::from_utf8(&buf) {
                    Ok(text) => text.trim().to_string(),
                    Err(_) => {
                        eprintln!("[docforge-engine] línea no UTF-8 recibida; decodificando con reemplazo");
                        String::from_utf8_lossy(&buf).trim().to_string()
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
                    let rpc_id = value
                        .get("rpcId")
                        .and_then(Value::as_str)
                        .map(str::to_owned);
                    if let Some(rpc_id) = rpc_id {
                        let result = if value.get("ok").and_then(Value::as_bool) == Some(true) {
                            Ok(value.get("result").cloned().unwrap_or(Value::Null))
                        } else {
                            Err(value.get("error").cloned().unwrap_or_else(|| {
                                serde_json::json!({
                                    "code": "INTERNAL",
                                    "message": "El motor devolvió un error RPC sin detalles."
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
                            // Never drop a task event silently (the UI would sit at 0 %):
                            // surface contract mismatches as a task error instead.
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
                                    .unwrap_or("El motor devolvió un error no reconocido.")
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
            if let Ok(mut state) = manager.inner.lock() {
                state.sender = None;
                let pending = std::mem::take(&mut state.pending);
                let error = serde_json::json!({
                    "code": "INTERNAL",
                    "message": "El sidecar se detuvo antes de responder."
                });
                for waiter in pending.into_values() {
                    let _ = waiter.send(Err(error.clone()));
                }
            }
            let ids = manager
                .inner
                .lock()
                .ok()
                .map(|state| state.in_flight.clone());
            if let Some(ids) = ids {
                let pending: Vec<String> = ids
                    .lock()
                    .map(|mut set| {
                        let list = set.iter().cloned().collect();
                        set.clear();
                        list
                    })
                    .unwrap_or_default();
                for id in pending {
                    let _ = app_for_wait.emit(
                        "task://event",
                        TaskEvent::Error {
                            id,
                            code: ErrorCode::Internal,
                            message: "El sidecar se detuvo; la tarea no terminó.".into(),
                            details: None,
                        },
                    );
                }
            }
            thread::sleep(Duration::from_millis(300));
            let _ = manager.ensure_running(&app_for_wait);
        });
        self.inner.lock().map_err(|e| e.to_string())?.sender = Some(tx);
        Ok(())
    }

    pub fn send_task(&self, app: &AppHandle, task: &ProcessorTask) -> Result<(), String> {
        self.ensure_running(app)?;
        let json = serde_json::to_string(task).map_err(|e| e.to_string())?;
        let state = self.inner.lock().map_err(|e| e.to_string())?;
        state
            .in_flight
            .lock()
            .map_err(|e| e.to_string())?
            .insert(task.id.clone());
        state
            .sender
            .as_ref()
            .ok_or_else(|| "El motor no está disponible".to_string())?
            .send(json)
            .map_err(|e| e.to_string())
    }
    pub fn cancel(&self, app: &AppHandle, id: &str) -> Result<(), String> {
        self.ensure_running(app)?;
        let message = serde_json::json!({ "type": "cancel", "id": id }).to_string();
        self.inner
            .lock()
            .map_err(|e| e.to_string())?
            .sender
            .as_ref()
            .ok_or_else(|| "El motor no está disponible".to_string())?
            .send(message)
            .map_err(|e| e.to_string())
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
        })
        .to_string();

        let sender = {
            let mut state = self.inner.lock().map_err(
                |error| serde_json::json!({ "code": "INTERNAL", "message": error.to_string() }),
            )?;
            state.pending.insert(rpc_id.clone(), tx);
            state.sender.clone().ok_or_else(|| {
                state.pending.remove(&rpc_id);
                serde_json::json!({
                    "code": "INTERNAL",
                    "message": "El motor no está disponible."
                })
            })?
        };

        if sender.send(message).is_err() {
            if let Ok(mut state) = self.inner.lock() {
                state.pending.remove(&rpc_id);
            }
            return Err(serde_json::json!({
                "code": "INTERNAL",
                "message": "No se pudo enviar la consulta al motor."
            }));
        }

        match rx.recv_timeout(timeout) {
            Ok(result) => result,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if let Ok(mut state) = self.inner.lock() {
                    state.pending.remove(&rpc_id);
                }
                Err(serde_json::json!({
                    "code": "TIMEOUT",
                    "message": "El motor tardó demasiado en responder a la consulta."
                }))
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => Err(serde_json::json!({
                "code": "INTERNAL",
                "message": "El canal RPC se cerró inesperadamente."
            })),
        }
    }

    pub fn health(&self, app: &AppHandle) -> Result<EngineHealth, String> {
        self.ensure_running(app)?;
        self.inner
            .lock()
            .map_err(|e| e.to_string())?
            .sender
            .as_ref()
            .ok_or_else(|| "El motor no está disponible".to_string())?
            .send(serde_json::json!({ "type": "health" }).to_string())
            .map_err(|e| e.to_string())?;
        Ok(self.inner.lock().map_err(|e| e.to_string())?.health.clone())
    }
}
