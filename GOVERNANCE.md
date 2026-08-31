# Governance

Kronos is an AGPL-3.0 project. This document describes how decisions are made and how contributions become part of the tree.

## Maintainers

The GitHub organization or user that owns [shn3g/kronos](https://github.com/shn3g/kronos) appoints maintainers. Maintainers merge pull requests, cut releases, and handle security reports described in [SECURITY.md](SECURITY.md).

## Decision process

1. Product architecture lives in `docs/architecture/`.
2. Behavior changes land as reviewable pull requests with tests.
3. License, security policy, and required checks need maintainer approval.
4. Disagreements that block a release are resolved by the owning maintainer until a broader maintainer group exists.

## Contribution license

All contributions are received under GNU AGPL v3.0 as stated in [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md). Maintainers will not relicense existing AGPL-3.0 code to a weaker license without a documented, contributor-approved process.

## Security

Security reports bypass the public issue tracker. Maintainers follow [SECURITY.md](SECURITY.md). Publishing a fix under AGPL-3.0 includes corresponding source for the patched version.

## Releases

Releases are git tags on `main`. Installers and SBOMs attach to GitHub Releases once packaging in later milestones is complete. Unsigned CI artifacts are for verification, not production distribution.

## Code of collaboration

- Keep discussion in GitHub issues, discussions, and pull requests so history stays public.
- Prefer small, tested changes over large unreviewed branches.
- Windows, macOS, and Linux remain first-class. A change that breaks one target needs a follow-up or a documented exception in the PR.
