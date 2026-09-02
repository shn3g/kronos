fn main() {
    // tauri_build validates bundle.resources before compile. The onedir is
    // gitignored and produced by scripts/build-engine.py; create an empty
    // placeholder so `cargo test` / clippy work without PyInstaller first.
    let engine_dir = std::path::Path::new("engine/kronos-engine");
    if !engine_dir.exists() {
        std::fs::create_dir_all(engine_dir).expect("create bundled engine resource dir");
    }
    println!("cargo:rerun-if-changed=engine/kronos-engine");
    tauri_build::build()
}
