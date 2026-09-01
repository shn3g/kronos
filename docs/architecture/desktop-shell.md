# Desktop shell

The Tauri 2 client in `apps/desktop` locates a loopback engine through `engine_connection` and probes `/health` plus `/version`. Without a sidecar (Vite/Playwright web preview), production wiring stays **engine unavailable**.

The window is an agent desktop, not a 12-page dashboard. File / Edit / View / Help sit in a menu bar. A 48px activity bar switches Chat, Workspaces, Files, and Settings. Chat is the main stage. Files edits one text file at a time. File → Go to file or Ctrl+P jumps to a path. Ctrl+F finds text in that file. Match case limits that search to the same letter case. Ctrl+H replaces it. Ctrl+G jumps to a line. Common languages are colored. Conversation history is a View toggle. A right inspector holds Changes, Goals, and Health. View can hide the activity bar and the inspector. View → Terminal (Ctrl+`) opens a real TTY under the chat.

If the local engine is down, the UI says so and does not open the app chrome. If the engine is ready and no planner model is assigned, Connect a model blocks the chrome. Vite `npm run dev` can use the same UI in a browser: the dev server proxies `/kronos-engine` to the loopback engine using `engine_ready.json` plus `install.json`, so the page never holds the bearer token. `vite preview` and Playwright do not enable that proxy, so they stay engine-unavailable. See [Agent desktop](agent-desktop.md).

## Playwright

The smoke test in `apps/desktop/tests/e2e` launches Chromium against the Vite production preview (`pnpm build` then `pnpm preview` on port 4173). Without a sidecar it asserts the engine-unavailable gate. It does not drive the native WebView. That choice keeps the check runnable without signing certificates. Native artifacts still build in the `desktop` CI job on Ubuntu, Windows, and macOS.
