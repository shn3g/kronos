# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://github.com/shn3g/kronos/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/shn3g/kronos/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/shn3g/kronos/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shn3g/kronos/releases/tag/v0.1.0
