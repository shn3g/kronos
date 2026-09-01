# Kronos

Local software-engineering OS. One desktop app enrols **your** git folder, plans bounded work, runs tests, and keeps repository automation under policy.

Windows, macOS, and Linux. Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

## Install

Download a Windows NSIS installer, Linux `.deb`, or macOS `.app` from a [GitHub Release](https://github.com/shn3g/kronos/releases) (`v0.2.0` is the current preview). Or build with `pnpm tauri build`.

Signing is not present. Windows SmartScreen and macOS Gatekeeper will warn. That is the OS. Use "Run anyway" or right-click Open for the unsigned path.

The desktop sidecar still runs `python -m kronos_engine` (`python` on Windows, `python3` elsewhere) from **PATH**. Python 3.11+ must be installed until a later bundle. An unsigned installer that does not bundle Python is not fully one-click.

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

1. Open Kronos. Engine ready requires the sidecar (`python -m kronos_engine` on PATH).
2. Workspaces: pick **your** git folder, Enrol. Kronos registers it in local SQLite. It does not write `.kronos/` into the tree at enrol.
3. Enable Kronos shows a **preview** of `.kronos/config.yaml`, workflow, and CODEOWNERS. You commit those on **your** repo.
4. Connections: two GitHub Apps (controller + isolated reviewer) and optional Telegram. Models: your keys in OS secret storage. Each role (orchestrator, planner, coder, reviewer, embedding) can be online or local.
5. Chat is the orchestrator: it answers questions and creates draft goals with `/goal`. It does not edit files or call GitHub.
6. Index: per-repo hybrid search under app cache. A watcher can reindex dirty working-tree files; unchanged chunk hashes skip re-embedding. FTS5 always; optional local ONNX or remote embeddings. Isolation by repository id. Weights are never downloaded.
7. On enrol: empty lesson store. Modes `write_draft_prs` and above also need the safety gate (branch protection, Kronos PR workflow, CODEOWNERS, verified reviewer app).
8. Leave `freeze: true` and `mode: observe` or `shadow` until you want writes.

**Skills:** global library under `skills/core/` shipped with Kronos. **Lessons:** per enrolled repo, empty at first, propose is not activate.

Retrieval is local hybrid search per repo.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [SECURITY.md](SECURITY.md).
