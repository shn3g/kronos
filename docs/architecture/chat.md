# Chat

Chat is the main stage of the 0.4.0 desktop. `ChatService` runs an agent loop against the assigned **orchestrator** profile. It streams tokens, may call tools inside the enrolled folder, and can create a draft goal with `/goal`. Executors still run unattended work under sandbox, modes, freeze, and budgets.

## What chat does

- Lists, creates, and loads conversations in local SQLite. `repository_id` may be null: a chat without a workspace can explain Kronos. Tools that need a folder return a clear sentence.
- Streams assistant text, tool cards, and goal readiness through the desktop Rust command `engine_stream`, or through `fetch` + `ReadableStream` in the Vite browser preview. The WebView never sees the bearer token or the engine port.
- Calls tools from a fenced code block whose language is `tool` (JSON, not native function calling): `search_index`, `list_files`, `read_file`, `write_file`, `run_command`, `search_memory`, `create_goal`, `list_goals`. Writes stay inside the enrolled realpath (no absolute paths, `..`, or `.git`; locked prefixes on write). Commands are capped and timeboxed. Chat does not `git push`.
- Accepts pasted images (png/jpeg/webp/gif, size and count capped) and `@file` mentions. Root `AGENTS.md`, `.cursorrules`, `CLAUDE.md`, and `.cursor/rules` are attached to the system prompt when a workspace is open.
- `/goal` creates a draft goal either way, then replies with readiness checks in plain sentences (workspace active, planner/coder/reviewer assigned, mode allows writes, GitHub controller, reviewer app, branch protection, Kronos PR workflow, CODEOWNERS, budget). The goal does not start the executor from chat.
- Path buttons in assistant text open the **Files** editor on that workspace-relative path.

## What chat does not do

- Call GitHub.
- Replace the Terminal panel. `run_command` is a one-shot, capped shell in the workspace folder; the Terminal PTY is interactive and separate (View menu).

## Streaming

Each SSE `data:` line is JSON:

- `{"delta": "text"}`
- `{"tool": {"id": "t1", "name": "read_file", "args": {...}, "status": "running"}}` then `{"tool": {"id": "t1", "name": "read_file", "status": "ok"|"error", "summary": "...", "output": "<clipped>"}}`
- `{"goal": {"id": "goal_x", "state": "draft", "can_execute": false, "readiness": [{"id","label","ok","detail"}]}}`
- `{"error": "sentence"}` (stream ends)
- `{"content": "...", "citations": [...], "goal_refs": [...], "done": true}`

Rust holds the token, reads SSE, and emits `engine-stream` events (`delta`, `tool`, `goal`, `error`, `done`). Cancel uses `engine_stream_cancel` plus `POST /conversations/{id}/cancel`. The browser preview uses the same paths through `/kronos-engine` with an `AbortController`.

## Configuration

Assign an orchestrator profile (Connect a model on first run, or the composer switcher). A billed provider with no key, or a cost ceiling of zero, fails closed (HTTP 409) instead of calling the network. Until 0.5.0 the engine on PATH must match the desktop version.
