# Desktop shell

The Tauri 2 client in `apps/desktop` locates a loopback engine through `engine_connection` and probes `/health` plus `/version`. Without a sidecar (Vite/Playwright web preview), production wiring stays **engine unavailable**.

## Playwright

The smoke test in `apps/desktop/tests/e2e` launches Chromium against the Vite production preview (`pnpm build` then `pnpm preview` on port 4173). Workspaces stays fail-closed without a sidecar. It does not drive the native WebView. That choice keeps CI independent of code signing and platform WebView setup. Native artifacts still build in the `desktop` CI job on Ubuntu, Windows, and macOS.
