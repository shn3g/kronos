# Kronos

Kronos is a local software-engineering operating system. One desktop application plans bounded work, runs tests, and keeps repository automation under deterministic policy.

This repository is licensed under the [GNU Affero General Public License v3.0](LICENSE). Kronos does not depend on Hermes.

Windows, macOS, and Linux are first-class targets. The desktop client talks to a version-matched local engine over a loopback API. Closing the window stops the sidecar child process started by Tauri.

## Status

The desktop shell, engine lifecycle, repository enrolment, model routing, GitHub Apps, Telegram, skills, and ops dashboard are present. Workspaces lists enrolled repositories after the engine is ready. Enable Kronos proposes a reviewable diff and does not write runtime files into the git tree. The production client fails closed: it reports **ready** only when the live loopback API is healthy and version-compatible.

See [docs/quickstart.md](docs/quickstart.md) and [docs/operations.md](docs/operations.md).

## Repository layout

```text
apps/desktop/          Tauri 2 + React + TypeScript shell
engine/                Python control-plane (loopback API, SQLite WAL)
services/reviewer/     Isolated reviewer placeholder
skills/                Future skill library
templates/             Repository policy and GitHub workflow templates
deploy/                Future service unit files
docs/                  Architecture, security, operations, and design plans
```

## Prerequisites

- Node.js 22 or newer
- [pnpm](https://pnpm.io/) 9.15 (see `packageManager` in `package.json`)
- Rust stable (for `pnpm tauri` native builds)
- Platform WebView libraries (WebView2 on Windows, WebKitGTK 4.1 on Linux)
- Visual Studio 2022 with the C++ workload on Windows (GitHub `windows-latest` provides this; a machine without MSVC can still run `pnpm test`, `pnpm test:e2e`, and engine pytest)
- Python 3.11 or newer for the engine

## Scripts

From the repository root:

| Command | What it runs |
| --- | --- |
| `pnpm install` | Install JavaScript workspace dependencies |
| `pnpm test` | Vitest unit tests for the desktop UI |
| `pnpm test:e2e` | Playwright smoke test against the Vite web build |
| `pnpm --filter @kronos/desktop dev` | Vite frontend on port 1420 |
| `pnpm --filter @kronos/desktop build` | Typecheck and Vite production bundle |
| `pnpm tauri dev` | Native Tauri window wrapping the Vite dev server |
| `pnpm tauri build` | Native installer/artifact for the current OS |
| `python -m pytest` (in `engine/`) | Engine unit and lifecycle tests |

Playwright targets the Vite web build (`vite preview` after `vite build`), not a full Tauri WebView. That keeps CI runnable without signing certificates. Native `tauri build` still runs in the desktop CI job when the runner has Rust and platform WebView libraries.

## Engine connection states

The shell displays exactly one of:

- **Engine unavailable**
- **Engine starting**
- **Engine ready**
- **Incompatible engine version**

Tests inject an `EngineClient`. The production client probes the live sidecar and fails closed to **unavailable** when the API is missing, unhealthy, or unreachable.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [SECURITY.md](SECURITY.md).
