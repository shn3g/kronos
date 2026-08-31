mod engine;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();
            let supervisor = engine::EngineSupervisor::spawn(&handle);
            app.manage(supervisor);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![engine::engine_connection])
        .run(tauri::generate_context!())
        .expect("Kronos failed to start");
}
