# Contributing to Kronos

Kronos is a local software-engineering operating system licensed under the [GNU Affero General Public License v3.0](LICENSE). By contributing, you license your work under AGPL-3.0 (or later, at the maintainers' option for future dual-licensing notices published in this file).

Hermes is not a dependency. Do not add Hermes packages, git submodules, or runtime imports.

## Development setup

1. Fork or clone this repository.
2. Install Node.js 22+, pnpm 9.15, and a stable Rust toolchain for native desktop builds.
3. Run `pnpm install` at the repository root.
4. Run `pnpm test` before opening a pull request.

Python 3.11+ is required for engine package work. This milestone's engine tree only exposes `__version__`.

## Tests first

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

## Pull requests

- Keep the change reviewable: one capability per PR when practical.
- Update README scripts when you add test or build entry points.
- Do not commit secrets, `.env` files, or machine-local paths.
- Sign each commit with `Signed-off-by` (`git commit -s`) to certify the [Developer Certificate of Origin](https://developercertificate.org/).

## Security

Report vulnerabilities through [SECURITY.md](SECURITY.md). Do not file public issues for unpatched exploits.

## License headers

New substantial source files should include a short AGPL-3.0 SPDX identifier:

```text
SPDX-License-Identifier: AGPL-3.0-or-later
```
