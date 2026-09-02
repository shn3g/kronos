# Desktop shell

The Tauri 2 client in `apps/desktop` locates a loopback engine through `engine_connection` and probes `/health` plus `/version`. Until 0.5.0 the engine on PATH must match the desktop version; a newer desktop against an older engine is **incompatible**. Without a sidecar (Vite `preview` / Playwright), production wiring stays **engine unavailable**.

## 0.3.0 frame

Gates first, then chrome. No Home page.

1. **Engine gate.** If the local engine is not ready, the UI shows the heading "The local engine is not running" (or "Starting Kronos") and does not open the menu bar or activity bar.
2. **Connect a model.** If the engine is ready and no **orchestrator** is assigned, Connect a model blocks the chrome. Presets include OpenAI, OpenRouter, OpenCode Zen, Ollama, and LM Studio. Connecting assigns all five roles from that provider. A workspace folder is not required to pass the gate.
3. **Shell.** File / Edit / View / Help sit in a menu bar. A 48px activity bar switches Chat, Files, Goals, Workspaces, and Settings. Chat is the main stage. Conversation history is a View toggle. The title row holds the workspace switcher and engine status. A right inspector holds Changes (read-only list of the working tree), Goals, and Health. View can hide the activity bar and the inspector.

Hash deep links: `#/chat`, `#/files`, `#/goals`, `#/workspaces`, `#/settings`, `#/settings/<section>`. Legacy hashes such as `#/models` rewrite into the Settings hub.

Settings hub sections: General, Models, Index, Connections (GitHub + Telegram), Skills, Memory, Updates, Notifications.

**Files is a placeholder** in 0.3.0 ("The editor arrives later"). Menu items that would open an editor (Go to file, Find, Replace, Go to line) switch to that placeholder. There is no Terminal panel in this release. Inspector Changes does not revert or commit; those HTTP routes exist on the engine for chat tools and later UI.

Vite `pnpm --filter @kronos/desktop dev` can use the same UI in a browser while `python -m kronos_engine` is running: the dev server proxies `/kronos-engine` using `engine_ready.json` plus `install.json`, so the page never holds the bearer token. `vite preview` and Playwright do not enable that proxy, so they stay engine-unavailable. See [Agent desktop](agent-desktop.md).

## Playwright

The smoke test in `apps/desktop/tests/e2e` launches Chromium against the Vite production preview (`pnpm build` then `pnpm preview` on port 4173). Without a sidecar it asserts the engine-unavailable gate sentence "The local engine is not running" and no menu bar. It does not drive the native WebView. That choice keeps the check runnable without signing certificates. Native artifacts still build in the `desktop` CI job on Ubuntu, Windows, and macOS.
