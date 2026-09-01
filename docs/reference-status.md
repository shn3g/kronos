# Kronos reference status

Do not merge this branch into `main`. It is a snapshot of the local `feat/desktop-agent-chat` line for a cloud model to read. `main` already has a different chat and orchestrator path (PR #13, tag `v0.2.0`).

Base of this branch: `f90c870` (public docs, unsigned installers, Klikday purged from git history). Head: current commit on `reference-do-not-merge`.

## What is already on `main` (do not re-implement)

Shipped through sub-plans 1 to 12, then public cleanup and later `main` work:

- Tauri 2 desktop + Vite React shell, Python 3.11+ FastAPI engine, SQLite WAL, bearer in Rust.
- Repository enrol with preview of `.kronos/config.yaml`, workflow, CODEOWNERS. Runtime state stays outside the enrolled tree.
- Model profiles, OS secret store, in-process sandbox. Cursor CLI / OpenAI-compatible / later OpenCode presets on `main`.
- Per-repo hybrid index (FTS5 always; embeddings evolved on `main` after this branch forked: real tokenizer, OpenAI-compatible embedder, watch, cache).
- GitHub controller App, isolated reviewer (`kronos-review (kronos-reviewer)`), staged autonomy modes, freeze, budgets, WIP, invert tests (comments and labels never merge).
- Goals / TDD path, skills library, propose-is-not-activate memory, Telegram, ops doctor / unsigned NSIS `.deb` `.app`.
- Public AGPL docs. No Klikday example pack. Releases `v0.1.0` and `v0.2.0` on GitHub.
- On `main` only (not in this branch): orchestrator conversations, SSE chat, `/goal` handoff, embedder identity, autonomy safety / issue hygiene / effort tiers (PR #13 and follow-ups).

## What this branch added (the delta vs `f90c870`)

Chat-first desktop agent, not a 12-page dashboard as the first screen.

### Shell

- Connect-a-model gate before chrome. Engine-unavailable gate if the sidecar is down.
- Activity bar: Chat, Workspaces, Files, Settings. Menu bar File / Edit / View / Help.
- Right inspector: Changes (default), Goals/Runs, Health. Rails can hide.
- Workspace switcher. Session context for the current folder.

### Chat (engine `application/chat.py` + desktop `features/chat`)

- Local sessions in SQLite. Streaming tokens. Stop / Escape / retry last prompt.
- Tools as fenced JSON: `search_index`, `read_file`, `write_file`, `run_command`, `search_memory`, `create_goal`, `list_goals`. Max six tool rounds. Writes capped. Commands capped per turn. Paths stay inside the enrolled root.
- `@` file mentions from the local index. AGENTS.md, `.cursorrules`, CLAUDE.md, `.cursor/rules` attached (root only, size-capped).
- Paste screenshots; send images to the connected model. Apply fenced code into the workspace. Copy fences. Context meter vs a 32k estimate; warn at 80 percent.
- Markdown rendering, tool cards, inline paths that open Files.

### Files, Terminal, Changes

- Files: tree, one-file editor, syntax color, line numbers, Find / Replace / Go to line, match case / whole word / regex, Ctrl+P, Ctrl+Shift+F (index), Ask in chat, Tab indent, quote selection into chat.
- Terminal: real TTY in the workspace folder, type, history, Stop. No engine secrets in that process.
- Changes: this-turn vs all dirty files, added/removed lines, Open, Revert (chat backup or HEAD), local Commit (no push).

### Browser preview

- `pnpm --filter @kronos/desktop dev` on port 1420. Vite proxies `/kronos-engine` using `engine_ready.json` + `install.json`. The page does not hold the bearer token.
- `vite preview` / Playwright do not enable that proxy.

### How to run this branch

Engine: `pip install -e ".[dev]"` in `engine/`, then `python -m kronos_engine`.

Desktop: `pnpm install` then `pnpm tauri dev`, or the Vite URL above.

Python 3.11+ must be on PATH. Node/Rust are for building or this preview, not for a downloaded installer from `main`.

## What is still missing

Product gaps vs the original standalone design, and vs a Cursor-class agent window:

- **Do not merge this onto `main` without a dedicated integration.** Two chat stacks exist. `main` is orchestrator + SSE. This branch is tool-fence chat + Files/Terminal/Changes. Combining them is a separate project.
- **Bundled Python.** Installers still call `python -m kronos_engine` from PATH. Design called for a bundled runtime.
- **Signed / notarized installers.** SmartScreen and Gatekeeper still warn.
- **Background engine vs window.** Design: closing the window does not stop scheduled work. Sidecar lifecycle is still tied to the desktop process in practice.
- **klikday-dashboard PRs 302 and 303** stay unmerged until that repo's hermes-reviewer check posts. Out of this repository. Do not bypass.
- **True one-click** and a hosted always-green Release for every tag (Actions has been spending-limited at times).
- **Docker / SWE-ReX as default sandbox.** In-process jail remains the default.
- **Live dogfood at 50 tasks / 30 days.** Harness exists; that evidence is not this PR.
- **Multi-task graphs in the UI**, tabbed IDE, hosted web app (browser preview is local only).
- **Embeddings ONNX weights** still not downloaded by this branch's older index path; `main` advanced embeddings after the fork.

## Intentional non-goals on this branch

- Not a Cursor IDE clone. One file in Files, not tabs.
- Hermes is not a dependency.
- Comments and labels still must not satisfy merge.
- This PR is reference only.
