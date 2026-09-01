# Agent desktop

Kronos is a locally installed desktop app (Tauri WebView, also previewable in a browser). It is not an operating system.

## Shell

- Application menu: File, Edit, View, Help. File holds New chat, Open workspace, Go to file, Save, Models, and Settings. Edit is Cut, Copy, Paste, Select all, Find, Replace, and Go to line.
- Collapsible icon activity bar on the left. View can also hide the Changes inspector.
- Chat is the main stage. Conversation history is a View toggle, not a permanent column.
- Workspace switcher lives in the title bar.
- A right drawer holds Changes, Goals/Runs, and Health as tabs. Changes is the default tab. Goals stay visible without forcing a goal form on every chat.
- Files edits one text file at a time. There is no tabbed IDE. Line numbers sit beside the text. Common languages are colored. Ctrl+F finds in the open file. Match case limits that search to the same letter case. Ctrl+H replaces in the open file. Ctrl+G jumps to a line.
- File → Go to file, or Ctrl+P / Cmd+P, jumps to a path in the current workspace. Unsaved Files edits stay when you switch to Chat.

## First run

1. If the local engine is not connected, show that fact. Do not open the 12-page dashboard.
2. If the engine is ready and no model provider is registered, block on Connect a model. API keys go to the OS secret store through the existing provider API.
3. A workspace folder is not required to pass the gate. Chat can explain Kronos. Opening a git folder starts indexing. The same UI can run in a browser preview while the local engine is running. The page talks through a same-origin proxy, so it never holds the engine token.

## Chat

Streaming conversation in the pane. Tokens appear as the model writes them. The agent may search the local per-repository index, read and write files inside the enrolled realpath, run a command in that folder, search active memories, and create a bounded Goal for unattended work. Root AGENTS.md, .cursorrules, CLAUDE.md, and files under .cursor/rules are attached to the system prompt on every turn, capped in size. Nested copies of those names are ignored. Apply on a fenced code block writes that file through the same chat write path, so it shows in Changes and can be reverted. Paste a screenshot into the composer. Kronos stores the file locally and sends it to the connected model as an image. Most turns stay in the thread. Tool calls render as named cards with a text status (done, failed, running). The user message appears as soon as Send is pressed. Stop closes the in-flight model request. The composer shows an estimated token count for this thread, including a small allowance for the system prompt. The count is an estimate, not the model's billed usage. At 80 percent of a 32,000 token window it asks you to start a new chat. The local index refreshes from git commits and from uncommitted files in enrolled folders.

## Research applied

This is how we design in Cursor, not a Kronos product. Sources: Cursor Agents Window, VS Code Agents Window, and Programming by Chat (arXiv:2604.00436).

- Progressive specification: no Goal form on every message. Short follow-ups stay in the same thread.
- Persistent plan: Goals tab is the place for unattended work, matching developers who pin a plan when a chat gets long.
- Review on the right: Changes is the default inspector tab (Cursor diffs, VS Code Changes panel). It lists the live git working tree. This turn shows files chat wrote and has not committed. All shows every dirty file. Revert restores the last chat write, or HEAD if chat did not write that file. Commit records a local git commit of the visible list and does not push. Open reads the file in Files for editing. Save or Ctrl+S writes it through the same workspace write path as chat Apply. Ctrl+P or File → Go to file jumps to a path without walking the tree. Ctrl+F finds text in the open file. Match case limits that search to the same letter case. Ctrl+H replaces it. Ctrl+G jumps to a line. Line numbers sit beside the editor. Common languages are colored. Ask in chat mentions the selected file. Click a file mention in chat, or an inline path in a reply, to open it in Files. Search contents uses the local index. The composer shows an estimated token count against a 32,000 token window. At 80 percent it asks you to start a new chat. Terminal is a View toggle and Ctrl+` panel. It opens a persistent shell in the current workspace folder and does not pass engine secrets into that process. Type a line and press Enter. Output stays as you send more lines. Up and Down recall previous lines from this session. Stop, or Escape in the command box, ends the shell.
- History is a View toggle, not a permanent column.

## Health

Settings and the Health tab share the same checks: engine, model, workspace, index, secrets. Each check has a label, ok flag, and a short sentence. Status is never color-only.

## Copy

Product text calls Kronos a desktop app. Signing warnings explain that Windows and macOS warn on unsigned installers, in plain language.
