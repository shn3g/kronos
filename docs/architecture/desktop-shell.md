# Desktop shell

The Tauri 2 client in `apps/desktop` is a local UI over an injected `EngineClient`. Production wiring returns **engine unavailable** until the engine milestone ships a live sidecar.

## Playwright

The smoke test in `apps/desktop/tests/e2e` launches Chromium against the Vite production preview (`pnpm build` then `pnpm preview` on port 4173). It does not drive the native WebView. That choice keeps CI independent of code signing and platform WebView setup. Native artifacts still build in the `desktop` CI job on Ubuntu, Windows, and macOS.
