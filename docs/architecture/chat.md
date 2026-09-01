# Chat orchestrator

Chat is the orchestrator, not a sidecar to goals. It answers basic questions itself (cheap model, capped tokens) using packed index context and citations. Anything that needs real work becomes a draft goal. Executors then run inside sandbox, modes, freeze, and budgets.

## What chat does

- Lists, creates, and loads per-repository conversations stored in local SQLite.
- Streams assistant text through the desktop Rust command `engine_stream`. The WebView never sees the bearer token or the engine port.
- Returns citations (path and line range) from the index context pack.
- `/goal` (and an orchestrator JSON intent the UI does not show) creates a draft goal. Chat does not start the executor.

## What chat does not do

- Edit files.
- Call GitHub.
- Invent tools. File writes, PRs, and merges stay on the goal/executor path.

## Streaming

The desktop Chat page calls Tauri `engine_stream` with an HTTP path on the loopback engine. Rust holds the token, reads SSE, and emits `engine-stream` events. Cancel uses `engine_stream_cancel`.

## Configuration

Assign an orchestrator profile on the Models page. A billed provider with no key, or a cost ceiling of zero, fails closed (HTTP 409) instead of calling the network.
