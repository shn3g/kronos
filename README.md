# Kronos

Local software-engineering OS. One desktop app enrols **your** git folder, plans bounded work, runs tests, and keeps repository automation under policy.

Windows, macOS, and Linux. Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

## Install

Download a Windows NSIS installer, Linux `.deb`, or macOS `.app` from a [GitHub Release](https://github.com/shn3g/kronos/releases) (`v0.4.0` is the current preview). Or build with `pnpm tauri build`.

Signing is not present. Windows SmartScreen and macOS Gatekeeper will warn. That is the OS. Use "Run anyway" or right-click Open for the unsigned path.

Installers bundle the local engine. You do not need Python on PATH to run them.

Hosted GitHub Actions may not always produce Release artifacts. If the Release has no installer, builders use the one-line build below.

## Build

Install Node 22, pnpm 9.15, Python 3.11+, Rust, and the platform WebView. Python is required to build the engine and for `python -m kronos_engine` during development; installers ship a bundled engine. Then:

```text
pnpm install
cd engine && pip install -e ".[dev]" && cd ..
python3 scripts/build-engine.py
pnpm tauri build
```

Contributor tests belong in [CONTRIBUTING.md](CONTRIBUTING.md). Walkthrough: [docs/quickstart.md](docs/quickstart.md).

## Inside the app

1. Open Kronos. If the local engine is down, the window says "The local engine is not running" and does not open chrome. Installers start a bundled `kronos-engine` sidecar; development builds may use `python -m kronos_engine` on PATH instead. Until 0.5.0 the engine **must match the desktop version**.
2. Connect a model if no orchestrator is assigned. Keys go into the operating system secret store. Chat is then the main stage (menu bar, activity bar, inspector). A workspace folder is optional.
3. Browser preview (same UI, no native window): start the engine, then `pnpm --filter @kronos/desktop dev` and open `http://localhost:1420`. The Vite `/kronos-engine` proxy adds the bearer on the server. `vite preview` stays engine-unavailable.
4. Open a git folder from File or Workspaces when you want indexing and file tools. Chat can search, read, write, and run capped commands inside that folder. `/goal` creates a draft and reports readiness. Chat does not call GitHub. **Files** edits in the activity bar; **Changes** in the inspector can revert or locally commit; **Terminal** (View menu) is a real shell in the workspace; **Goals** is a workbench with Plan/Tick and readiness links.
5. Enable Kronos shows a **preview** of `.kronos/config.yaml`, workflow, and CODEOWNERS. You commit those on **your** repo.
6. Connections: two GitHub Apps (controller + isolated reviewer) and optional Telegram. Models: each role (orchestrator, planner, coder, reviewer, embedding) can be online or local.
7. Index: per-repo hybrid search under app cache. A watcher can reindex dirty working-tree files; unchanged chunk hashes skip re-embedding. FTS5 always; optional local ONNX or remote embeddings. Isolation by repository id. Weights are never downloaded.
8. On enrol: empty lesson store. Modes `write_draft_prs` and above also need the safety gate (branch protection, Kronos PR workflow, CODEOWNERS, verified reviewer app). Leave `freeze: true` and `mode: observe` or `shadow` until you want autonomous writes.

**Skills:** global library under `skills/core/` shipped with Kronos. **Lessons:** per enrolled repo, empty at first, propose is not activate.

Retrieval is local hybrid search per repo.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [SECURITY.md](SECURITY.md).
