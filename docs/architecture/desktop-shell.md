# Desktop shell

The Tauri 2 client in `apps/desktop` locates a loopback engine through `engine_connection` and probes `/health` plus `/version`. Installers bundle a `kronos-engine` sidecar; development builds may use `python -m kronos_engine` on PATH instead. A dev PATH engine should match the desktop version; a newer desktop against an older engine is **incompatible**. Without a sidecar (Vite `preview` / Playwright smoke), production wiring stays **engine unavailable**.

## 0.5.0 frame

Gates first, then chrome. No Home page.

1. **Engine gate.** Installers start the bundled sidecar. If the local engine is not ready, the UI shows "Starting Kronos" or "The local engine is not running" and does not open the menu bar or activity bar.
2. **Connect a model.** If the engine is ready and no **orchestrator** is assigned, Connect a model blocks the chrome. Presets include OpenAI, OpenRouter, OpenCode Zen, Ollama, and LM Studio, or any OpenAI-compatible URL. API keys are optional for local endpoints. Connecting assigns all five roles from that provider. A workspace folder is not required to pass the gate.
3. **Shell.** File / Edit / View / Help sit in a menu bar. A 48px activity bar switches Chat, Files, Goals, Workspaces, and Settings. Chat is the main stage. Conversation history is a View toggle. The title row holds the workspace switcher and engine status. A right inspector holds Changes (working tree with Revert and local commit), Goals/Runs, and Health. View can hide the activity bar and the inspector, and open the Terminal panel.

Hash deep links: `#/chat`, `#/files`, `#/goals`, `#/workspaces`, `#/settings`, `#/settings/<section>`. Legacy hashes such as `#/models` rewrite into the Settings hub.

Settings hub sections: General, Models, Index, Connections (GitHub + Telegram), Skills, Memory, Updates, Notifications.

**Files** is a full editor with tree, tabs, Go to file palette, Find/Replace/Go to line, Ask in chat, and save via the workspace files API. **Terminal** (View menu) is a real PTY in the enrolled folder. Inspector **Changes** can revert paths and record a local git commit (Kronos does not push).

Settings → Models includes local embeddings install (MiniLM or bge-small, SHA-256 pinned catalog). Settings → Updates checks GitHub Releases `latest.json` and verifies bundle signatures with the publisher minisign public key.

Vite `pnpm --filter @kronos/desktop dev` can use the same UI in a browser while the engine is running: the dev server proxies `/kronos-engine` using `engine_ready.json` plus `install.json`, so the page never holds the bearer token. `vite preview` and Playwright smoke do not enable that proxy, so they stay engine-unavailable. See [Agent desktop](agent-desktop.md).

## Playwright

The default smoke test in `apps/desktop/tests/e2e` launches Chromium against the Vite production preview (`pnpm build` then `pnpm preview` on port 4173). Without a sidecar it asserts the engine-unavailable gate sentence "The local engine is not running" and no menu bar. It does not drive the native WebView. That choice keeps the check runnable without signing certificates.

On Linux CI, after smoke passes on a ready-for-review pull request, `pnpm test:e2e:engine` (`KRONOS_E2E_ENGINE=1`) runs the **with-engine** project: a real `python3 -m kronos_engine` sidecar and a mock OpenAI-compatible model. That exercises Connect a model, Chat, Files, Changes, Terminal, and Goals workbench in the browser build. Native artifacts still build in the `desktop` CI job on Ubuntu, Windows, and macOS.
