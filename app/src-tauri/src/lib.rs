mod commands;
mod contract;
mod sidecar;
use commands::AppState;
use sidecar::SidecarManager;
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            sidecar: SidecarManager::new(),
        })
        .invoke_handler(tauri::generate_handler![
            commands::run_task,
            commands::cancel_task,
            commands::engine_health,
            commands::check_system_health,
            commands::set_default_output_dir,
            commands::get_default_output_dir,
            commands::engine_rpc,
            commands::reveal_in_folder,
            commands::notify_desktop
        ])
        .run(tauri::generate_context!())
        .expect("error while running DocForge Desktop");
}
