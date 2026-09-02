# Engine lifecycle

The Tauri shell starts a bundled `kronos-engine` binary from app resources (or `KRONOS_ENGINE_BIN` / a sibling `kronos-engine` binary, or `python -m kronos_engine` during development) as a child process. The child binds loopback, authenticates with a per-install bearer token, and writes SQLite WAL state under application data. Desktop `createProductionEngineClient` reports **ready** only after `/health` is ok and `/version` says the desktop client is compatible. Sidecar spawn failure stays **unavailable**.
