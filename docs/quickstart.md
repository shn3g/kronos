# Quickstart

Kronos is a local software-engineering operating system. One desktop application plans bounded work, runs tests, and keeps repository automation under committed policy.

This project is licensed under GNU AGPL v3.0. Kronos does not depend on Hermes.

## Install

1. Install Node.js 22+, pnpm 9.15, Python 3.11+, and a stable Rust toolchain for native desktop builds.
2. Clone this repository and run `pnpm install` at the repository root.
3. From `engine/`, install the engine package in development mode (`pip install -e ".[dev]"`).
4. Run `pnpm test` and `python -m pytest` (from `engine/`) before you change behavior.

Windows, macOS, and Linux are first-class. A signed production installer is a later operator step. Unsigned CI artifacts are for verification.

## Enable a repository

1. Start the desktop app or the local engine sidecar.
2. Enrol a git repository. Enable Kronos shows a preview of `.kronos/config.yaml`, `.github/workflows/kronos-pr.yml`, and CODEOWNERS. Preview does not write the tree.
3. Review and commit those files through a normal pull request. CODEOWNERS must cover `.kronos/**`.
4. Connect the controller GitHub App and the isolated reviewer GitHub App. Workers never receive those credentials.
5. Leave autonomy frozen (`freeze: true`) and `mode: observe` or `mode: shadow` until you are ready for writes.

The integration branch comes from committed `.kronos/config.yaml`. The in-app template default is `main`. The protected default branch is `policy.branches.protected` (template default `main`).

## Staged modes

Models cannot change the mode. Operators raise it through reviewed policy.

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

From the repository root: `pnpm test`. From `engine/`: `python -m pytest`. Fixtures only. Do not point tests at live GitHub or Telegram.

## Next reading

- [Architecture](architecture/README.md)
- [Threat model](security/threat-model.md)
- [Operations and rollback](operations.md)
