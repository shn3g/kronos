# Desktop shell

The Tauri 2 client in `apps/desktop` locates a loopback engine through `engine_connection` and probes `/health` plus `/version`. Without a sidecar (Vite/Playwright web preview), production wiring stays **engine unavailable**.

The window is an agent desktop, not a 12-page dashboard. File / Edit / View / Help sit in a menu bar. A 48px activity bar switches Chat, Workspaces, Index, and Settings. Chat is the main stage. Conversation history is a View toggle. A right inspector holds Changes, Goals, and Health.

If the engine is down, the UI says so and does not open the app chrome. If the engine is ready and no planner model is assigned, Connect a model blocks the chrome. See [Agent desktop](agent-desktop.md).

## Playwright

The smoke test in `apps/desktop/tests/e2e` launches Chromium against the Vite production preview (`pnpm build` then `pnpm preview` on port 4173). Without a sidecar it asserts the engine-unavailable gate. It does not drive the native WebView. That choice keeps the check runnable without signing certificates. Native artifacts still build in the `desktop` CI job on Ubuntu, Windows, and macOS.
