# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Local span tracing no longer rewrites `spans.jsonl` on every HTTP request (append-only, size-capped, off by default for request spans), which was thrashing disks while the app sat idle.
- Engine log files rotate (`RotatingFileHandler`) instead of growing without bound.
- Desktop respawns the local engine after a crash with backoff instead of staying permanently unavailable until a full app relaunch.
- Workspace inspect/enrol errors surface the engine's detail (for example "not a git repository") instead of a generic failure string.

### Changed

- Workspaces primary action is **Add workspace** with copy that matches indexing, chat, and Goals (not "proposes reviewable files only").
- Engine status and gate copy talk about Kronos starting/stopping, not an exposed "engine" server metaphor.

### Notes

- **0.5.0 cannot self-update to 0.5.1.** Builds shipped with an empty updater pubkey, so Check for updates stayed disabled. Install 0.5.1 (or newer) manually from GitHub Releases once, then in-app updates work.

## [0.5.1] - 2026-09-03

First-run gates, reliable chat replies, and headless-safe local model secrets.

### Fixed

- Chat no longer treats empty streams as success; engine errors show in the UI; Retry sits under the last reply instead of floating after every turn.
- Tauri no longer emits a silent empty `done` when the SSE connection closes early.
- Connect a model marks hosted presets as billed and gives billed providers a non-zero cost ceiling so chat is not blocked with a 409.
- Local (unbilled) models and repo inspect no longer fail when the OS credential store is missing (headless CI and some Linux installs).

### Changed

- First run is a three-step gate: connect a model → install local embeddings (mandatory) → optional workspace.
- Max tokens moved under Advanced on Settings → Models; `max_tokens` is omitted from provider requests when set to 0.
- Chat stage and composer share a wider aligned column.

## [0.5.0] - 2026-09-02

One-click install, agent chat, local embeddings, and signed in-app updates (fail-closed until the owner installs a publisher pubkey).

### Added

- **Bundled engine:** installers ship a PyInstaller `kronos-engine` sidecar so Python is not required on PATH. Development builds may still use `python -m kronos_engine` when the sidecar is absent.
- **Local embeddings install:** Settings → Models can download MiniLM or bge-small from a pinned catalog on click. Each file is verified with SHA-256 before it is activated.
- **Signed updater:** Settings → Updates checks GitHub Releases `latest.json` through Rust IPC. NSIS uses per-user (`currentUser`) install mode. Linux updater bundles use the signed AppImage. Check for updates stays disabled until `plugins.updater.pubkey` in `tauri.conf.json`, `UPDATER_PUBKEY`, and GitHub secrets `TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` are set by the owner. Users never generate keys.
- **First-run polish:** bundled engine gate clears quickly, Connect a model presets (key optional for local endpoints), keyboard map in Help, streaming accessibility, and notification badge on Settings.

### Changed

- README and quickstart Install sections describe download, run, and connect a model. Dev PATH engines should still match the desktop version.
- Threat model documents embedding downloads and the in-app updater (pinned URLs, SHA-256, minisign pubkey, fail-closed empty pubkey). Unsigned SmartScreen/Gatekeeper warnings remain.

## [0.4.0] - 2026-09-02

Workbench: Files editor, Changes revert/commit, Health, Terminal, Goals workbench, and full-stack Playwright on Linux CI. Not one-click yet (no bundled engine, embeddings installer, or updater - those are 0.5.0).

### Added

- **Files activity:** tree, editor tabs, Go to file palette, Find/Replace/Go to line, Ask in chat on a selection, and Save through the workspace files API.
- **Inspector Changes:** Revert per path and local git commit from the working-tree list (Kronos does not push to GitHub).
- **Health tab:** doctor checks from `GET /ops/doctor` with local fallbacks for engine, model, workspace, index, secrets, and embeddings.
- **Terminal panel:** real PTY in the enrolled workspace folder (View menu).
- **Goals workbench:** goal list, planned steps, Plan and Tick, read-only autonomy mode, readiness from `GET /repositories/{id}/goal-readiness` with Settings fix links, and runs filtered by the selected goal.
- **Linux CI:** `pnpm test:e2e:engine` (real engine plus mock OpenAI) after the smoke test on ready-for-review pull requests.

### Changed

- Chat path buttons open the Files editor on that path instead of a placeholder.
- CI and security workflows still run on ready-for-review pull requests only, not on push to `main`.

### Fixed

- Files tree indentation uses `--tree-depth`.
- Terminal and chat `run_command` share the same `run_key` on the engine.
- Stale goal readiness clears when the selected goal changes.

## [0.3.0] - 2026-09-02

Agent shell: Cursor-like desktop plus agentic chat. Files editor, Terminal, inspector revert/commit, Goals workbench, and a bundled engine are later releases.

### Added

- Cursor-like window: menu bar (File, Edit, View, Help), activity bar (Chat, Files, Goals, Workspaces, Settings), title-row workspace switcher, and a right inspector (Changes, Goals, Health). Engine-unavailable and Connect-a-model gates run before chrome. Connect a model assigns the **orchestrator** (and the other roles from the same provider). Files is a placeholder in this release.
- Agentic chat: tools (`search_index`, `list_files`, `read_file`, `write_file`, `run_command`, `search_memory`, `create_goal`, `list_goals`), SSE tool and goal events, cancel, pasted images, `@file` mentions, token meter, and a composer model switcher. Chat writes files through tools inside the enrolled folder.
- Browser preview through Vite `/kronos-engine` (bearer added on the dev server, never in the page). `vite preview` stays engine-unavailable.
- Workspace HTTP: files list and contents, working-tree changes, local commit, and revert (engine plus Rust allowlist). Inspector Changes is **read-only** in this release.
- `/goal` replies include readiness checks (workspace, models, mode/freeze, GitHub controller, reviewer app, branch protection, PR workflow, CODEOWNERS, budgets).

### Changed

- CI and security workflows run on ready-for-review pull requests, not on push to `main`. Draft PRs keep version lockstep only. Installers still publish from `v*` tags. Ubuntu desktop CI also runs `cargo test` and clippy.

### Fixed

- A desktop newer than the engine on PATH is now reported as incompatible instead of ready. The status banner shows both versions (`Engine ready. Desktop 0.3.0. Engine 0.3.0.`) and the incompatible message names the PATH engine to install.

## [0.2.0] - 2026-09-01

Developed as 0.1.1–0.1.6 on this branch; tagged together as 0.2.0.

### Added

- Local embeddings use a real tokenizer. Optional MiniLM ONNX weights already on disk, an OpenAI-compatible embedding HTTP adapter, a registry embedding role, and memory backfill into the index.
- Continuous indexing: a file watcher, dirty working-tree files, chunk-hash skip for unchanged embeddings, progress, and a watch toggle.
- Orchestrator model role. Provider presets for OpenAI, OpenRouter, OpenCode Zen (`https://opencode.ai/zen/v1`), Ollama, and LM Studio. Cost ceiling in the Models UI. Streamed completions. Per-repository executor (`controlled`, `cursor`, or `opencode`). LLM planner with IndexedPlanner as the deterministic fallback.
- Chat orchestrator HTTP API and desktop Chat page. Streaming goes through Rust `engine_stream`. `/goal` creates draft goals. Chat does not edit files or call GitHub.
- Safety gate before `write_draft_prs` and higher (branch protection, Kronos PR workflow, CODEOWNERS, reviewer app). GitHub issue and pull request templates and labels. Effort tiers. Lessons included in executor and planner context.

### Changed

- Each model role (orchestrator, planner, coder, reviewer, embedding) can use an online API or a local OpenAI-compatible endpoint on its own.
- Sparse FTS5 search stays available when dense embeddings are missing.

### Fixed

- Embedding adapters fail closed on bad responses. Backfill batches stay independent.
- Index watcher honors git commits, per-repo debounce, and idle probes so watch does not load embedders. Stale search hits are ignored.
- Chat returns 409 when billed secrets are missing, hides planner intent JSON, and the desktop stream/load race is fixed.

## [0.1.0] - 2026-09-01

First public desktop preview (`v0.1.0`). Enrol a git folder, leave freeze and observe/shadow until you want writes, unsigned Windows/Linux/macOS installers.

[unreleased]: https://github.com/shn3g/kronos/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/shn3g/kronos/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/shn3g/kronos/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/shn3g/kronos/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/shn3g/kronos/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/shn3g/kronos/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shn3g/kronos/releases/tag/v0.1.0
