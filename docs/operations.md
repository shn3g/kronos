# Operations

Kronos is the documented source of truth for prior automation going forward. Public GitHub visibility for `shn3g/kronos` is a controller step after this work is approved and merged. Do not flip visibility from a feature branch.

## Staged cutover

1. Commit `examples/removed/config.yaml` as `.kronos/config.yaml` on `main-openclaw` (shadow or observe).
2. Import `examples/removed/lessons.yaml` as disabled candidates.
3. Run the comparison harness (`kronos_engine.domain.comparison`) on fixture dispatch/merge decisions. Hard failures: default-branch writes, reviewer-identity misses (comment or label), duplicate external writes, secret-shaped payloads.
4. Raise `autonomy.mode` only through reviewed policy. Models cannot change it.
5. Keep prior `scripts/agent-ops` and merge-gate in place as the operator fallback.

## Rollback

Freeze Kronos autonomy and leave prior wrappers as fallback. Do not re-enable write crons from this procedure. The contain change that paused write-capable wrappers stays unmerged until its own review.

Engine API for freeze:

1. Call `rollback_to_wrappers` for the enrolled repository id (pauses the repo and sets `autonomy.freeze: true`).
2. Leave `mode` unchanged unless you also commit a policy change to `observe`.
3. Confirm dispatch refuses at the freeze step and that no GitHub issues, pull requests, or merges are created.
4. Use prior wrappers only as a manual operator fallback. Do not turn write crons back on.

Tests: `engine/tests/unit/application/test_migration_rollback.py`.

## Removing embedded automation

Delete `scripts/agent-ops` and related prior factory crons only after **two stable Kronos release cycles** with:

- Zero default-branch writes
- Zero reviewer-identity misses
- Zero duplicate external writes
- Zero secret-shaped payloads in recorded outcomes

That cleanup is a dedicated prior PR. Do not mass-delete wrappers in the shadow-config change.

## Doctor, backup, install

See `docs/architecture/engine.md` and `deploy/`. Doctor backup excludes the OS secret store. Restore fails closed on missing or corrupt archives. Unsigned releases still ship checksums, SBOM, and provenance. Claiming a signed release without `release.sig` fails closed.

## HTTP allowlist

The Rust sidecar allows loopback engine paths used by Desktop. `/ops/token` and `/ops/pem` stay denied. Bearer stays in Rust.
