# Contributing to Kronos

Kronos is a local software-engineering operating system licensed under the [GNU Affero General Public License v3.0](LICENSE). By contributing, you license your work under the same AGPL-3.0 terms.

Hermes is not a dependency. Do not add Hermes packages, submodules, or runtime imports.

## Development setup

1. Fork or clone [shn3g/kronos](https://github.com/shn3g/kronos).
2. Install:
   - Node.js 22 or newer
   - [pnpm](https://pnpm.io/) 9.15 (see `packageManager` in `package.json`)
   - Rust stable (for `pnpm tauri` native builds)
   - Python 3.11 or newer for the engine
   - Platform WebView libraries (WebView2 on Windows, WebKitGTK 4.1 on Linux)
   - Visual Studio 2022 with the C++ workload on Windows (GitHub `windows-latest` provides this; a machine without MSVC can still run `pnpm test`, `pnpm test:e2e`, and engine pytest)
3. Run `pnpm install` at the repository root.
4. From `engine/`, install the engine package in development mode: `pip install -e ".[dev]"`.

Windows, macOS, and Linux are first-class targets.

## Tests

This file is the source of truth for contributor test commands.

From the repository root:

```text
pnpm test
pnpm test:e2e
```

`pnpm test` runs Vitest unit tests for the desktop UI. `pnpm test:e2e` runs the Playwright smoke test against the Vite web build (`vite preview` after `vite build`), not a native Tauri WebView. That keeps the check runnable without signing certificates. Native `tauri build` still runs in the desktop CI job when the runner has Rust and platform WebView libraries.

On Linux CI, Chromium is installed with `pnpm exec playwright install --with-deps chromium` in `apps/desktop` before `pnpm test:e2e`. Install the Playwright browser locally if the smoke test reports that it is missing.

From `engine/`:

```text
python -m pytest
python -m ruff check src tests
python -m mypy
```

Run the commands that cover the code you changed before you open a pull request.

### Tests first

Behavior changes follow red-green-refactor:

1. Add or update a failing test that names the behavior.
2. Confirm the test fails for the missing behavior, not a typo.
3. Write the minimum production code to pass.
4. Refactor while tests stay green.

Config, lockfiles, and generated Tauri icon binaries are exempt from red-green ceremony. User-visible states (engine connection, routing shell) are not.

Never mock the production engine client as **ready** without a live engine. Tests may inject a client that returns **ready** so the UI for that state can be asserted.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat(desktop): show engine unavailable by default
```

Types: `feat`, `fix`, `docs`, `test`, `ci`, `chore`, `refactor`, `perf`. Keep the subject under 72 characters. User-facing copy in the product and in commit subjects uses ASCII hyphens, not em dashes.

Sign each commit with `Signed-off-by` (`git commit -s`) to certify the [Developer Certificate of Origin](https://developercertificate.org/). There is no CLA and no extra signed-commit requirement beyond that DCO sign-off.

## Pull requests

- Keep the change reviewable: one capability per PR when practical.
- Do not commit secrets, `.env` files, or machine-local paths.
- If you add a test or lint entry point, document it in the Tests section above.
- Pull requests run `.github/workflows/ci.yml` (frontend tests on Ubuntu, Windows, and macOS; Playwright smoke on Linux; desktop native builds; engine pytest, ruff, and mypy) and `.github/workflows/security.yml` (dependency audit, secret scanning, SBOM). Keep those jobs green.
- This repository does not currently include a `.github/CODEOWNERS` file. Changes to license, security policy, and required-check configuration need maintainer approval. See [GOVERNANCE.md](GOVERNANCE.md).

## Security

Report vulnerabilities through [SECURITY.md](SECURITY.md). Do not file public issues for unpatched exploits.

## License headers

New substantial source files should include a short AGPL-3.0 SPDX identifier:

```text
SPDX-License-Identifier: AGPL-3.0-or-later
```
