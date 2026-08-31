# Kronos

Kronos is a local software-engineering operating system. One desktop application plans bounded work, runs tests, and keeps repository automation under deterministic policy.

This repository is licensed under the [GNU Affero General Public License v3.0](LICENSE). Kronos does not depend on Hermes.

Windows, macOS, and Linux are first-class targets. The desktop client talks to a version-matched local engine. Closing the window does not define engine lifetime; engine lifecycle lands in a later milestone.

## Status

The current tree is the desktop shell: routes, design tokens, and engine connection states. The engine placeholder exposes `__version__` only. Production desktop wiring reports **engine unavailable** until a live engine exists. The UI can also render **starting**, **ready**, and **incompatible version** when an injected client returns those states. A default session never reports **ready**.

## Repository layout

```text
apps/desktop/          Tauri 2 + React + TypeScript shell
engine/                Python package placeholder (__version__ only)
services/reviewer/     Isolated reviewer placeholder
skills/                Future skill library
templates/             Future repository and GitHub templates
deploy/                Future service unit files
docs/                  Architecture, security, research, and design plans
```

## Prerequisites

- Node.js 22 or newer
- [pnpm](https://pnpm.io/) 9.15 (see `packageManager` in `package.json`)
- Rust stable (for `pnpm tauri` native builds)
- Python 3.11 or newer (engine package metadata only in this milestone)

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

Playwright targets the Vite web build (`vite preview` after `vite build`), not a full Tauri WebView. That keeps CI runnable without signing certificates. Native `tauri build` still runs in the desktop CI job when the runner has Rust and platform WebView libraries.

## Engine connection states

The shell displays exactly one of:

- **Engine unavailable**
- **Engine starting**
- **Engine ready**
- **Incompatible engine version**

Tests inject an `EngineClient`. The production client fails closed to **unavailable**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [SECURITY.md](SECURITY.md).
