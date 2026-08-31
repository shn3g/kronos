# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent reviewer process entry. Cannot push or merge."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.attestations import ATTESTATION_HMAC_KEY_REF
from kronos_engine.ports.secrets import SecretStore
from kronos_reviewer.attestation import build_attestation
from kronos_reviewer.auth import ReviewerAuth
from kronos_reviewer.check_run import ReviewerCheckClient
from kronos_reviewer.checkout import ReviewGit, fetch_review_refs, materialize_head
from kronos_reviewer.policy import load_trusted_policy
from kronos_reviewer.verification import CommandRunner, VerificationError, verify_change


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    pull_number: int
    head_sha: str
    base_sha: str
    worktree: Path


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    ok: bool
    reason: str


def review_pull(
    request: ReviewRequest,
    *,
    git: ReviewGit,
    runner: CommandRunner,
    auth: ReviewerAuth,
    checks: ReviewerCheckClient,
    secrets: SecretStore,
) -> ReviewOutcome:
    scoped = auth.mint()
    fetch_review_refs(git, head_sha=request.head_sha, base_sha=request.base_sha)
    materialize_head(git, head_sha=request.head_sha, dest=request.worktree)
    policy = load_trusted_policy(git, base_sha=request.base_sha, head_sha=request.head_sha)
    changed = git.changed_files(request.base_sha, request.head_sha)
    try:
        verification = verify_change(
            policy=policy,
            changed_files=changed,
            proposed_risk=policy.risk.floor,
            runner=runner,
            worktree=request.worktree,
        )
    except VerificationError as error:
        return ReviewOutcome(ok=False, reason=str(error))
    key = secrets.get(ATTESTATION_HMAC_KEY_REF)
    if not key:
        return ReviewOutcome(ok=False, reason="reviewer attestation key is missing")
    attestation = build_attestation(
        run_id=f"pr-{request.pull_number}-{request.head_sha[:12]}",
        head_sha=request.head_sha,
        base_sha=request.base_sha,
        reviewer_app_id=checks.app_id,
        commands=tuple(item.argv for item in verification.commands),
        risk=verification.risk,
        hmac_key=key.encode(),
    )
    _ = attestation
    checks.post_success(
        head_sha=request.head_sha,
        summary="independent review passed",
        token=scoped.require_fresh(),
    )
    return ReviewOutcome(ok=True, reason="reviewed")


def main(argv: Sequence[str] | None = None) -> None:
    _ = argv
    raise SystemExit("kronos-reviewer requires injected git, sandbox, and App credentials")
