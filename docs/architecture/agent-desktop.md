# Agent desktop

Kronos is a locally installed desktop app (Tauri WebView, also previewable in a browser). It is not an operating system.

## Shell

- Application menu: File, Edit, View, Help.
- Collapsible icon activity bar on the left.
- Chat is the main stage. Conversation history is a View toggle, not a permanent column.
- Workspace switcher lives in the title bar.
- A right drawer holds Changes, Goals/Runs, and Health as tabs. Changes is the default tab. Goals stay visible without forcing a goal form on every chat.
- No code editor or tabs in this slice.

## First run

1. If the local engine is not connected, show that fact. Do not open the 12-page dashboard.
2. If the engine is ready and no model provider is registered, block on Connect a model. API keys go to the OS secret store through the existing provider API.
3. A workspace folder is not required to pass the gate. Chat can explain Kronos. Opening a git folder starts indexing.

## Chat

Streaming conversation in the pane. The agent may search the local per-repository index, read and write files inside the enrolled realpath, search active memories, and create a bounded Goal for unattended work. Most turns stay in the thread. Tool calls render as named cards with a text status (done, failed, running). The user message appears as soon as Send is pressed. Stop asks the engine to cancel the current turn between model steps.

## Research applied

This is how we design in Cursor, not a Kronos product. Sources: Cursor Agents Window, VS Code Agents Window, and Programming by Chat (arXiv:2604.00436).

- Progressive specification: no Goal form on every message. Short follow-ups stay in the same thread.
- Persistent plan: Goals tab is the place for unattended work, matching developers who pin a plan when a chat gets long.
- Review on the right: Changes is the default inspector tab (Cursor diffs, VS Code Changes panel). Files tree, last-turn filter, commit, terminal, and context meter stay later.
- History is a View toggle, not a permanent column.

## Health

Settings and the Health tab share the same checks: engine, model, workspace, index, secrets. Each check has a label, ok flag, and a short sentence. Status is never color-only.

## Copy

Product text calls Kronos a desktop app. Signing warnings explain that Windows and macOS warn on unsigned installers, in plain language.
