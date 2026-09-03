# Operations

Kronos is a local control plane for enrolled repositories.

## Policy and lessons

1. Commit `.kronos/config.yaml` through a reviewed pull request. Leave `autonomy.mode` at `observe` or `shadow` until the operator is ready for writes. The integration branch is a policy field, not an autonomy mode.
2. Import lessons YAML as `disabled_candidate` records. Propose is not activate.
3. Run the comparison harness (`kronos_engine.domain.comparison`) on fixture dispatch/merge decisions. Hard failures: default-branch writes, reviewer-identity misses (comment or label), duplicate external writes, secret-shaped payloads.
4. Raise `autonomy.mode` only through reviewed policy. Models cannot change it.

## Rollback

Freeze Kronos autonomy. Do not re-enable write crons from this procedure.

Engine API for freeze:

1. Call `rollback_to_wrappers` for the enrolled repository id (pauses the repo and sets `autonomy.freeze: true`).
2. Leave `mode` unchanged unless you also commit a policy change to `observe`.
3. Confirm dispatch refuses at the freeze step and that no GitHub issues, pull requests, or merges are created.
4. Do not turn write crons back on. `wrappers_reenabled` stays false.

Tests: `engine/tests/unit/application/test_migration_rollback.py`.

## Prior automation

Leave existing operator fallbacks in place until two stable Kronos release cycles with:

- Zero default-branch writes
- Zero reviewer-identity misses
- Zero duplicate external writes
- Zero secret-shaped payloads in recorded outcomes

Do not mass-delete those fallbacks in the same change that enables Kronos policy.

## Doctor, backup, install, updates

See `docs/architecture/engine.md` and `deploy/`. Doctor backup excludes the OS secret store. Restore fails closed on missing or corrupt archives. Unsigned releases still ship checksums, SBOM, and provenance. Claiming a signed release without `release.sig` fails closed.

Windows NSIS installers use per-user (`currentUser`) install mode so in-app updates can upgrade the existing install without elevation. Linux updater bundles use the signed AppImage artifact; the `.deb` remains the manual download for package-manager installs. **v0.5.0 cannot self-update** because it shipped with an empty publisher pubkey; operators must install `v0.5.1` or newer from GitHub Releases once. From 0.5.1 onward, in-app updates verify `latest.json` with the publisher minisign public key. Do not leave a public key whose private half is missing: `pnpm tauri build` then fails on every CI desktop job. End users never generate minisign keys.

CI and Security workflows run when a pull request is marked **ready for review** (draft PRs do not burn Actions minutes). Merging to `main` does not re-run those jobs. Full installer builds run from `release.yml` on `v*` tags.

Local embeddings install only on explicit click from Settings → Models, using pinned URLs and SHA-256 verification (see `docs/security/threat-model.md`).

The desktop **Health** tab and Settings **Run doctor** call `GET /ops/doctor` on the local engine. Checks cover engine readiness, assigned models, enrolled workspace, index health, secrets storage, and embeddings configuration. Failed goal-readiness items in the Goals workbench link to the Settings section that fixes them (models, connections, workspaces). Inspector Changes can revert or locally commit working-tree files; Kronos does not push to GitHub from those actions.

## HTTP allowlist

The Rust sidecar allows loopback engine paths used by Desktop. `/ops/token` and `/ops/pem` stay denied. Bearer stays in Rust.
