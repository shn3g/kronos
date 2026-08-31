# Threat model

Kronos treats untrusted issues, code, web results, logs, and imported skills as data. Merge identity is a GitHub App check on the exact head SHA. Comments and labels never satisfy merge.

## Trust boundaries

- **Desktop / Telegram / CLI:** operator UI. Same application services. No raw GitHub or reviewer credentials in messages.
- **Engine:** local control plane. SQLite WAL, loopback HTTP, bearer in the Rust sidecar. Domain has no I/O.
- **Controller GitHub App:** opens draft PRs to the integration branch, stamps provenance, never posts the required reviewer check.
- **Reviewer GitHub App:** isolated process and filesystem. Loads trusted policy from the pull request base. Publishes one App-bound check. Cannot push or merge.
- **Coding worker:** secret-free sandbox, worktree under application cache. Cannot approve itself.

Workers never receive controller or reviewer credentials.

## Invert contracts (must fail)

These klikday-era paths must not succeed in Kronos:

1. Bot-authored verdict comments as merge identity.
2. `security-reviewed` labels as merge identity.
3. Reviewer posting with `GH_TOKEN` or ambient `gh` auth.
4. Required checks that omit `integration_id` or set `strict_required_status_checks_policy: false`.
5. Autonomous merge to the protected default branch.
6. `coder_may_merge` / `pulse_may_merge` in policy (unrepresentable).
7. Hermes check names (`security-review (hermes-reviewer)`).
8. Dry-run consuming attempt budget unless the operator sets `budgets.dry_run_meters`.
9. Scheduled spawn without a claimed task id.
10. Worktrees, metrics, traces, or `TICKET.md` committed into the enrolled git tree.

## Staged writes

Observe and shadow modes must not create GitHub issues, pull requests, or merges. Higher modes still refuse default-branch writes. Models cannot change `autonomy.mode`.

## Secrets

Bearer tokens stay in the Rust sidecar. Engine HTTP does not expose `/ops/token` or `/ops/pem`. Recorder and backup redaction strip PEMs, GitHub tokens, bot tokens, and high-entropy secrets. Attestations cannot carry `GH_TOKEN` or hidden chain-of-thought.

## Reporting

See [SECURITY.md](../../SECURITY.md). Do not file public issues for unpatched exploits.
