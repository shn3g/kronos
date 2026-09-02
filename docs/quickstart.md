# Quickstart

Kronos is a local software-engineering operating system. One desktop application plans bounded work, runs tests, and keeps repository automation under committed policy.

Windows, macOS, and Linux. Licensed under GNU AGPL v3.0.

## Install

Download a Windows NSIS installer, Linux `.deb`, or macOS `.app` from a [GitHub Release](https://github.com/shn3g/kronos/releases) (`v0.3.0` is the current preview).

Signing is not present. Windows SmartScreen and macOS Gatekeeper will warn. That is the OS. Use "Run anyway" or right-click Open for the unsigned path.

The desktop sidecar still runs `python -m kronos_engine` (`python` on Windows, `python3` elsewhere) from PATH. Python 3.11+ must be installed until a later bundle. An unsigned installer that does not bundle Python is not fully one-click.

Hosted GitHub Actions may not always produce Release artifacts. If the Release has no installer, install Node 22, pnpm 9.15, Python 3.11+, Rust, and the platform WebView, then:

```text
pnpm install
cd engine && pip install -e ".[dev]" && cd ..
pnpm tauri build
```

## First run

1. Open Kronos. If the local engine is down, the window says "The local engine is not running". The sidecar is `python -m kronos_engine` on PATH. Until 0.5.0 the engine **must match the desktop version**.
2. Connect a model if no orchestrator is assigned. Keys go into the operating system secret store.
3. Chat is the main stage without a folder. Open a git folder from File or Workspaces when you want indexing and file tools. Chat can search, read, write, and run capped commands inside that folder. `/goal` creates a draft and reports readiness. Paste a screenshot into chat to ask about the UI.
4. Browser preview: start the engine, then `pnpm --filter @kronos/desktop dev` and open `http://localhost:1420`. The page never sees the engine token. `vite preview` stays engine-unavailable.
5. Kronos registers enrolled folders in local SQLite. It does not write `.kronos/` into the tree at enrol.
6. Optional later: enable a committed `.kronos/config.yaml` (preview of config, `.github/workflows/kronos-pr.yml`, and CODEOWNERS; you commit those on your repo; CODEOWNERS must cover `.kronos/**`), GitHub Apps, and Telegram. Leave `freeze: true` and `mode: observe` or `shadow` until you want autonomous git writes.

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
