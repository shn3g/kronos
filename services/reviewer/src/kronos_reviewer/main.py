# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent reviewer process entry. Cannot push or merge."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.attestations import ATTESTATION_HMAC_KEY_REF
from kronos_engine.domain.github import REVIEWER_PRIVATE_KEY_REF
from kronos_engine.domain.policy import PolicyError
from kronos_engine.ports.forge import AppCredentials
from kronos_engine.ports.secrets import SecretStore

from kronos_reviewer.attestation import build_attestation
from kronos_reviewer.auth import ReviewerAuth
from kronos_reviewer.check_run import ReviewerCheckClient
from kronos_reviewer.checkout import (
    GitInstallationFetch,
    ReviewGit,
    fetch_review_refs,
    materialize_head,
)
from kronos_reviewer.http import HttpTransport, HttpxTransport
from kronos_reviewer.policy import PolicySourceError, load_trusted_policy
from kronos_reviewer.verification import (
    CommandRunner,
    FreshProcessRunner,
    VerificationError,
    verify_change,
)


class ReviewerComposeError(RuntimeError):
    """Raised when reviewer composition is missing required secrets or identity."""


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


@dataclass(frozen=True, slots=True)
class ReviewerDeps:
    git: ReviewGit
    runner: CommandRunner
    auth: ReviewerAuth
    checks: ReviewerCheckClient
    secrets: SecretStore


class FileSecretStore:
    def __init__(self, files: Mapping[str, Path]) -> None:
        self._files = dict(files)

    def put(self, name: str, value: str) -> None:
        _ = name
        _ = value
        raise ReviewerComposeError("reviewer secret store is read-only")

    def get(self, name: str) -> str | None:
        path = self._files.get(name)
        if path is None or not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip()

    def delete(self, name: str) -> None:
        _ = name
        raise ReviewerComposeError("reviewer secret store is read-only")


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
    try:
        policy = load_trusted_policy(
            git, base_sha=request.base_sha, head_sha=request.head_sha
        )
    except (PolicyError, PolicySourceError) as error:
        return ReviewOutcome(ok=False, reason=str(error))
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
        commands=verification.commands,
        risk=verification.risk,
        hmac_key=key.encode(),
    )
    checks.post_success(
        head_sha=request.head_sha,
        summary="independent review passed",
        token=scoped.require_fresh(),
        attestation=attestation,
    )
    return ReviewOutcome(ok=True, reason="reviewed")


def compose_reviewer(
    *,
    environ: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
) -> ReviewerDeps:
    env = environ if environ is not None else os.environ
    owner = (env.get("KRONOS_GITHUB_OWNER") or "").strip()
    repo = (env.get("KRONOS_GITHUB_REPO") or "").strip()
    app_id_raw = (env.get("KRONOS_REVIEWER_APP_ID") or "").strip()
    installation_raw = (env.get("KRONOS_REVIEWER_INSTALLATION_ID") or "").strip()
    pem_file = (env.get("KRONOS_REVIEWER_PRIVATE_KEY_FILE") or "").strip()
    attest_file = (env.get("KRONOS_REVIEWER_ATTESTATION_KEY_FILE") or "").strip()
    remote = (env.get("KRONOS_REVIEWER_REMOTE") or "").strip()
    store = (env.get("KRONOS_REVIEWER_GIT_STORE") or "").strip()
    if not owner:
        raise ReviewerComposeError("missing reviewer composition: owner")
    if not repo:
        raise ReviewerComposeError("missing reviewer composition: repo")
    if not app_id_raw.isdigit() or not installation_raw.isdigit():
        raise ReviewerComposeError("missing reviewer composition: App ids")
    if not pem_file or not attest_file:
        raise ReviewerComposeError("missing reviewer composition: credentials")
    if not remote or not store:
        raise ReviewerComposeError("missing reviewer composition: git store")
    secrets = FileSecretStore(
        {
            REVIEWER_PRIVATE_KEY_REF: Path(pem_file),
            ATTESTATION_HMAC_KEY_REF: Path(attest_file),
        }
    )
    if not secrets.get(REVIEWER_PRIVATE_KEY_REF):
        raise ReviewerComposeError("missing reviewer composition: credentials")
    if not secrets.get(ATTESTATION_HMAC_KEY_REF):
        raise ReviewerComposeError("missing reviewer composition: credentials")
    http = transport or HttpxTransport()
    credentials = AppCredentials(
        app_id=int(app_id_raw),
        installation_id=int(installation_raw),
        role="reviewer",
    )
    auth = ReviewerAuth(secrets=secrets, credentials=credentials, transport=http)
    token = auth.mint().require_fresh()
    git = GitInstallationFetch(remote_url=remote, token=token, store=Path(store))
    checks = ReviewerCheckClient(
        transport=http,
        app_id=int(app_id_raw),
        owner=owner,
        repo=repo,
    )
    return ReviewerDeps(
        git=git,
        runner=FreshProcessRunner(),
        auth=auth,
        checks=checks,
        secrets=secrets,
    )


def main(argv: Sequence[str] | None = None) -> None:
    _ = argv
    try:
        compose_reviewer()
    except ReviewerComposeError as error:
        raise SystemExit(str(error)) from error
    raise SystemExit("kronos-reviewer: missing pull review arguments")
