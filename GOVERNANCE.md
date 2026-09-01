# Governance

Kronos is an AGPL-3.0 project. This document describes how decisions are made and how contributions become part of the tree.

## Maintainers

Maintainers are appointed by the owner of [https://github.com/shn3g/kronos](https://github.com/shn3g/kronos). Maintainers merge pull requests, cut releases, and handle security reports described in [SECURITY.md](SECURITY.md).

## Decision process

1. Product architecture lives in `docs/architecture/` only.
2. Behavior changes land as reviewed pull requests with tests.
3. License, security policy, and required checks need maintainer approval.
4. Disagreements that block a release are resolved by the owning maintainer until a broader maintainer group exists.

## Contribution license

All contributions are received under GNU AGPL v3.0 as stated in [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md). Maintainers will not relicense existing AGPL-3.0 code to a weaker license without a documented, contributor-approved process.

## Security

Security reports follow [SECURITY.md](SECURITY.md). They bypass the public issue tracker. Publishing a fix under AGPL-3.0 includes corresponding source for the patched version.

## Releases

Releases are git tags on `main` (`v0.1.0`, then `v0.1.1`, `v0.2.0`, and so on). Kronos uses [Semantic Versioning](https://semver.org/). `0.x` is preview: public installers may exist, the product is not 1.0, and APIs may change. GitHub still publishes `0.x` as the latest release so the download is visible. `1.0.0` is the first stable line.

The version Cursor and the desktop app read is `0.2.0` in `apps/desktop/src-tauri/tauri.conf.json`, kept in lockstep with `package.json`, `apps/desktop/src-tauri/Cargo.toml`, `engine/pyproject.toml`, and `services/reviewer/pyproject.toml`. `scripts/check-version-sync.py` fails CI when those files disagree.

Unsigned NSIS / `.deb` / `.app` installers and `SHA256SUMS` attach to GitHub Releases. SBOM and provenance stay on the Actions run. Signing is optional and fail-closed without a key.

## Code of collaboration

- Keep discussion in GitHub issues, discussions, and pull requests so history stays public.
- Prefer small, tested changes over large unreviewed branches.
- Windows, macOS, and Linux are first-class. A change that breaks one target needs a follow-up or a documented exception in the pull request.
