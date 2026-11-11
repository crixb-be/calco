use crate::{
    contract::{EngineHealth, ProcessorTask},
    sidecar::SidecarManager,
};
use serde_json::Value;
use serde::Serialize;
use std::{
    env,
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use std::time::Duration;
use tauri::{AppHandle, State};
use uuid::Uuid;
pub struct AppState {
    pub sidecar: SidecarManager,
}
#[tauri::command]
pub fn run_task(
    app: AppHandle,
    state: State<'_, AppState>,
    mut task: ProcessorTask,
) -> Result<ProcessorTask, String> {
    if task.id.is_empty() {
        task.id = Uuid::new_v4().to_string();
    }
    if task.engine.is_empty() || task.action.is_empty() || task.output_dir.is_empty() {
        return Err("INVALID_TASK: faltan engine, action u outputDir".into());
    }
    if !Path::new(&task.output_dir).is_absolute() || !Path::new(&task.output_dir).exists() {
        return Err("INVALID_TASK: outputDir debe ser una carpeta existente y absoluta".into());
    }
    for input in &task.input_files {
        if !Path::new(input).is_absolute() || !Path::new(input).exists() {
            return Err(format!("INPUT_NOT_FOUND: {input}"));
        }
    }
    state.sidecar.send_task(&app, &task)?;
    Ok(task)
}
#[tauri::command]
pub fn cancel_task(app: AppHandle, state: State<'_, AppState>, id: String) -> Result<(), String> {
    state.sidecar.cancel(&app, &id)
}
#[tauri::command]
pub fn engine_health(app: AppHandle, state: State<'_, AppState>) -> Result<EngineHealth, String> {
    state.sidecar.health(&app)
}

#[derive(Debug, Serialize)]
pub struct SystemHealth {
    pub sidecar_online: bool,
    pub libreoffice_path: Option<String>,
    pub disk_free_bytes: Option<u64>,
}

fn libreoffice_path() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    for variable in ["ProgramFiles", "ProgramFiles(x86)"] {
        if let Some(root) = env::var_os(variable) {
            candidates.push(PathBuf::from(root).join("LibreOffice/program/soffice.exe"));
        }
    }
    if let Ok(output) = Command::new("where.exe").arg("soffice.exe").output() {
        if output.status.success() {
            if let Some(path) = String::from_utf8_lossy(&output.stdout).lines().find(|line| !line.trim().is_empty()) {
                candidates.push(PathBuf::from(path.trim()));
            }
        }
    }
    candidates.into_iter().find(|path| path.is_file())
}

fn disk_free_bytes() -> Option<u64> {
    #[cfg(windows)]
    {
        let drive = env::current_dir().ok()?.to_string_lossy().chars().next()?.to_string();
        let command = format!("(Get-PSDrive -Name '{}').Free", drive);
        let output = Command::new("powershell.exe")
            .args(["-NoProfile", "-NonInteractive", "-Command", &command])
            .output()
            .ok()?;
        if !output.status.success() {
            return None;
        }
        return String::from_utf8_lossy(&output.stdout).trim().parse().ok();
    }
    #[cfg(not(windows))]
    {
        None
    }
}

#[tauri::command]
pub fn check_system_health(app: AppHandle, state: State<'_, AppState>) -> SystemHealth {
    SystemHealth {
        sidecar_online: state.sidecar.health(&app).is_ok(),
        libreoffice_path: libreoffice_path().map(|path| path.to_string_lossy().into_owned()),
        disk_free_bytes: disk_free_bytes(),
    }
}

fn settings_path() -> PathBuf {
    let root = env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    root.join("DocForge").join("settings.json")
}

#[tauri::command]
pub fn set_default_output_dir(path: String) -> Result<String, String> {
    let selected = PathBuf::from(&path);
    if !selected.is_absolute() || !selected.is_dir() {
        return Err("La carpeta de salida debe existir y ser una ruta absoluta".into());
    }
    let destination = settings_path();
    fs::create_dir_all(destination.parent().unwrap_or_else(|| Path::new(".")))
        .map_err(|error| error.to_string())?;
    let temporary = destination.with_extension("json.tmp");
    let payload = serde_json::json!({ "defaultOutputDir": selected.to_string_lossy() });
    fs::write(&temporary, serde_json::to_vec_pretty(&payload).map_err(|error| error.to_string())?)
        .map_err(|error| error.to_string())?;
    fs::rename(&temporary, &destination).map_err(|error| error.to_string())?;
    Ok(selected.to_string_lossy().into_owned())
}

#[tauri::command]
pub fn get_default_output_dir() -> Result<Option<String>, String> {
    let path = settings_path();
    if !path.is_file() {
        return Ok(None);
    }
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let value: Value = serde_json::from_str(&raw).map_err(|error| error.to_string())?;
    Ok(value.get("defaultOutputDir").and_then(Value::as_str).map(str::to_owned))
}

#[tauri::command]
pub async fn engine_rpc(
    app: AppHandle,
    state: State<'_, AppState>,
    method: String,
    params: Value,
) -> Result<Value, String> {
    let sidecar = state.sidecar.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        sidecar.rpc(&app, method, params, Duration::from_secs(30))
    })
    .await
    .map_err(|error| {
        serde_json::json!({
            "code": "INTERNAL",
            "message": format!("No se pudo esperar la respuesta RPC: {error}")
        })
        .to_string()
    })?;
    result.map_err(|error| error.to_string())
}

#[tauri::command]
pub fn reveal_in_folder(path: String) -> Result<(), String> {
    let target = Path::new(&path);
    let dir = if target.is_dir() {
        target.to_path_buf()
    } else {
        target
            .parent()
            .ok_or_else(|| "Ruta sin carpeta padre".to_string())?
            .to_path_buf()
    };
    #[cfg(windows)]
    {
        let mut command = std::process::Command::new("explorer");
        if target.is_file() {
            command.arg(format!("/select,{}", target.display()));
        } else {
            command.arg(&dir);
        }
        let child = command.spawn().map_err(|e| e.to_string())?;
        drop(child);
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        std::process::Command::new("xdg-open")
            .arg(dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Native desktop notification without holding a child-process handle. Windows uses the
/// built-in ToastNotificationManager; other platforms remain best-effort no-ops in dev.
#[tauri::command]
pub fn notify_desktop(title: String, body: String) -> Result<(), String> {
    #[cfg(windows)]
    {
        let script = r#"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text id="1"></text><text id="2"></text></binding></visual></toast>')
$xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode($env:DOCFORGE_NOTIFICATION_TITLE)) | Out-Null
$xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode($env:DOCFORGE_NOTIFICATION_BODY)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DocForge Desktop').Show($toast)
"#;
        let child = std::process::Command::new("powershell.exe")
            .args(["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script])
            .env("DOCFORGE_NOTIFICATION_TITLE", title)
            .env("DOCFORGE_NOTIFICATION_BODY", body)
            .spawn()
            .map_err(|error| format!("No se pudo iniciar la notificación: {error}"))?;
        drop(child);
    }
    #[cfg(not(windows))]
    {
        let _ = (title, body);
    }
    Ok(())
}
