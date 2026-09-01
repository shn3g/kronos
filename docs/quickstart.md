# Quickstart

Kronos is a locally installed desktop app for coding agents. You pick a git folder, connect a model, and work in a chat window. The app can search a local index, start longer goals, and run tests under committed policy.

Windows, macOS, and Linux. Licensed under GNU AGPL v3.0.

## Install

Download a Windows NSIS installer, Linux `.deb`, or macOS `.app` from a [GitHub Release](https://github.com/shn3g/kronos/releases) (`v0.1.0` is the current preview).

Installers are not code-signed yet. Windows SmartScreen and macOS Gatekeeper will warn because they do not recognize the publisher. If you built this release or trust the download, choose Run anyway on Windows, or Open on macOS.

The desktop sidecar still runs `python -m kronos_engine` (`python` on Windows, `python3` elsewhere) from PATH. Python 3.11+ must be installed until a later bundle. An unsigned installer that does not bundle Python is not fully one-click.

Hosted GitHub Actions may not always produce Release artifacts. If the Release has no installer, install Node 22, pnpm 9.15, Python 3.11+, Rust, and the platform WebView, then:

```text
pnpm install
cd engine && pip install -e ".[dev]" && cd ..
pnpm tauri build
```

## First run

1. Open Kronos. The window waits for the local engine (`python -m kronos_engine` on PATH).
2. Connect a model if none is assigned. Keys go into the operating system secret store.
3. Chat is ready without a folder. Open a git folder from File or the workspace control when you want indexing and file edits. AGENTS.md, .cursorrules, and files under .cursor/rules in that folder are followed on every chat turn. Paste a screenshot into chat to ask about the UI.
4. Kronos registers enrolled folders in local SQLite. It does not write `.kronos/` into the tree at enrol.
5. Optional later: enable a committed `.kronos/config.yaml`, GitHub Apps, and Telegram. Leave `freeze: true` and `mode: observe` or `shadow` until you want autonomous git writes.

The integration branch comes from committed `.kronos/config.yaml`. The in-app template default is `main`. The protected default branch is `policy.branches.protected` (template default `main`).

Skills are a global library under `skills/core/` shipped with Kronos. Lessons are per enrolled repo, empty at first. Propose is not activate. Retrieval is local hybrid search per repo.

## Staged modes

Models cannot change the mode. You raise it through reviewed policy.

| Mode | GitHub issues | Draft PRs | Integration merge | Multi-task graphs |
| --- | --- | --- | --- | --- |
| `observe` | no | no | no | no |
| `shadow` | no | no | no | no |
| `write_issues` | yes | no | no | no |
| `write_draft_prs` | yes | yes | no | no |
| `merge_integration` | yes | yes | yes, integration only | no |
| `multi_task` | yes | yes | yes, integration only | yes |

Every mode refuses autonomous writes to the protected default branch.

## Tests

See [CONTRIBUTING.md](../CONTRIBUTING.md). Fixtures only. Do not point tests at live GitHub or Telegram.

## Next reading

- [Architecture](architecture/README.md)
- [Threat model](security/threat-model.md)
- [Operations and rollback](operations.md)
