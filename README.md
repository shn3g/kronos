# Kronos

Local software-engineering OS. One desktop app enrols **your** git folder, plans bounded work, runs tests, and keeps repository automation under policy.

Windows, macOS, and Linux. Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

## Install

Download a Windows NSIS installer, Linux `.deb` or AppImage, or macOS `.app` from a [GitHub Release](https://github.com/shn3g/kronos/releases) (`v0.5.1` is the current preview). Or build with `pnpm tauri build`.

**If you are on 0.5.0:** that build cannot self-update (empty updater pubkey). Download and install `v0.5.1` or newer manually once; later updates can use Settings → Updates.
Signing is not present. Windows SmartScreen and macOS Gatekeeper will warn. That is the OS. Use "Run anyway" or right-click Open for the unsigned path.

Installers bundle the local engine. You do not need Python on PATH to run them. Download, run Kronos, and connect a model (presets or any OpenAI-compatible URL; API key optional for local endpoints).

Hosted GitHub Actions may not always produce Release artifacts. If the Release has no installer, builders use the one-line build below.

## Build

Install Node 22, pnpm 9.15, Python 3.11+, Rust, and the platform WebView. Python is required to build the engine and for `python -m kronos_engine` during development; installers ship a bundled engine. Then:

```text
pnpm install
cd engine && pip install -e ".[dev]" pyinstaller && cd ..
python3 scripts/build-engine.py
pnpm tauri build
```

Contributor tests belong in [CONTRIBUTING.md](CONTRIBUTING.md). Walkthrough: [docs/quickstart.md](docs/quickstart.md).

## Inside the app

1. Open Kronos. Installers start a bundled `kronos-engine` sidecar within seconds. Development builds may use `python -m kronos_engine` on PATH instead; that engine should match the desktop version.
2. Connect a model if no orchestrator is assigned. Use a preset, any OpenAI-compatible URL, or a one-liner (`openai gpt-4o-mini key sk-…`). Keys go into the operating system secret store. Chat is then the main stage. Change models later in Settings → Models (chat does not reassign providers).
3. Browser preview (same UI, no native window): start the engine, then `pnpm --filter @kronos/desktop dev` and open `http://localhost:1420`. The Vite `/kronos-engine` proxy adds the bearer on the server. `vite preview` stays engine-unavailable.
4. **File → Open Folder** (or Workspaces → Add workspace) enrols a git folder for indexing and file tools. The title bar shows Indexing… / Indexed. Chat can search, read, write, and run capped commands inside that folder. `/goal` creates a draft and reports readiness; goal completion needs verification evidence (passing gates), not silent success.
5. **Files** edits in the activity bar; **Changes** in the inspector can revert or locally commit; **Terminal** (View menu) is a real shell in the workspace; **Goals** is a workbench with Plan/Tick and readiness links.
6. Connections: two GitHub Apps (controller + isolated reviewer) and optional Telegram. Models: each role (orchestrator, planner, coder, reviewer, embedding) can be online or local.
7. Index runs in the background under a supervised worker. Hybrid search lives under app cache. Optional local ONNX embeddings install from Settings → Models (SHA-256 pinned catalog). Isolation by repository id.
8. Updates: Settings → Updates can check GitHub Releases when the owner configures signing. Until a publisher pubkey is set, the check stays disabled (fail closed).
9. Optional later: commit `.kronos/config.yaml`, workflow, and CODEOWNERS on **your** repo for write modes. Leave `freeze: true` and `mode: observe` or `shadow` until you want autonomous writes.

**Skills:** global library under `skills/core/` shipped with Kronos. **Lessons:** per enrolled repo, empty at first, propose is not activate.

Retrieval is local hybrid search per repo.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [SECURITY.md](SECURITY.md).
