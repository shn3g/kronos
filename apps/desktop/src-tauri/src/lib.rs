mod engine;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let supervisor = engine::EngineSupervisor::spawn(&handle);
            app.manage(supervisor);
            app.manage(engine::StreamCancels::default());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            engine::engine_state,
            engine::engine_json,
            engine::engine_stream,
            engine::engine_stream_cancel,
            engine::pick_repository_folder,
            engine::import_telegram_bot_token
        ])
        .run(tauri::generate_context!())
        .expect("Kronos failed to start");
}
