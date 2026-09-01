# Kronos

A locally installed desktop app for coding agents. You pick a git folder, connect a model, and work in a chat window. Kronos can search a local index of that folder, start longer goals, and run tests. You can also open the same UI in a browser preview.

Windows, macOS, and Linux. Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

## Install

Download a Windows NSIS installer, Linux `.deb`, or macOS `.app` from a [GitHub Release](https://github.com/shn3g/kronos/releases) (`v0.1.0` is the current preview). Or build with `pnpm tauri build`.

Installers are not code-signed yet. Windows SmartScreen and macOS Gatekeeper will warn because they do not recognize the publisher. If you built this release or trust the download, choose Run anyway on Windows, or Open on macOS.

The desktop sidecar still runs `python -m kronos_engine` (`python` on Windows, `python3` elsewhere) from **PATH**. Python 3.11+ must be installed until a later bundle includes it. An unsigned installer that does not bundle Python is not fully one-click.

Hosted GitHub Actions may not always produce Release artifacts. If the Release has no installer, builders use the one-line build below.

## Build

Install Node 22, pnpm 9.15, Python 3.11+, Rust, and the platform WebView. Then:

```text
pnpm install
cd engine && pip install -e ".[dev]" && cd ..
pnpm tauri build
```

Contributor tests belong in [CONTRIBUTING.md](CONTRIBUTING.md). Walkthrough: [docs/quickstart.md](docs/quickstart.md).

## Inside the app

1. If no model is connected, Kronos asks for one before the main window. Keys go into the operating system secret store.
2. Chat is the main window. File, Edit, View, and Help are in the menu bar. The left icon bar switches Chat, Workspaces, Index, and Settings. You can hide that bar and the Changes inspector from View. The same UI can run in a browser at `http://localhost:1420` while `python -m kronos_engine` is running on this machine. The browser never sees the engine token.
3. Open a git folder from File or the workspace control. Kronos indexes it locally. Chat can search, read, and write files inside that folder.
4. Changes from chat writes show in the right inspector. Revert restores the last chat write for that file. Health ticks cover engine, model, workspace, index, and secrets.
5. Memories live in Settings. Unattended work can become a Goal from chat.

**Skills:** global library under `skills/core/` shipped with Kronos. **Lessons:** per enrolled repo, empty at first, propose is not activate.

Retrieval is local hybrid search per repo.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [SECURITY.md](SECURITY.md).
