# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration merge after independent review. Promotion PRs are never auto-merged."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from kronos_engine.domain.attestations import (
    POSTED_BY_CONTROLLER,
    POSTED_BY_FOREIGN,
    POSTED_BY_REVIEWER,
    POSTED_BY_WORKER,
    AttestationError,
    CheckRunIdentity,
    CommentEvidence,
    MergeDecision,
    MergeEvidence,
    RunAttestation,
    evaluate_merge_policy,
    parse_attestation,
    required_commands_from_repository,
)
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.domain.policy import PolicyError, parse_policy
from kronos_engine.domain.policy_yaml import parse_simple_yaml
from kronos_engine.ports.forge import DefaultBranchWriteRefused, ForgeError, IdempotencyKey, PullRef

POLICY_PATH = ".kronos/config.yaml"


class MergeRefused(RuntimeError):
    """Raised when merge policy refuses an integration merge."""


class MergePort(Protocol):
    integration_branch: str
    protected_branch: str

    def merge_pull(self, number: int, *, sha: str, dest: str | None = None) -> None: ...

    def open_pull(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool,
        key: IdempotencyKey,
    ) -> PullRef: ...

    def get_pull(self, number: int) -> PullRef: ...

    def list_check_runs(self, sha: str) -> Sequence[Mapping[str, object]]: ...

    def list_issue_comments(self, number: int) -> Sequence[Mapping[str, object]]: ...

    def list_issue_labels(self, number: int) -> Sequence[str]: ...

    def ruleset_strict(self) -> bool: ...

    def review_threads_resolved(self, number: int) -> bool: ...

    def file_at_sha(self, sha: str, path: str) -> str: ...


@dataclass(frozen=True, slots=True)
class PromotionRef:
    pull: PullRef
    merged: bool


def promotion_pr_auto_merge_allowed() -> bool:
    return False


def check_identity_from_github(
    raw: Mapping[str, object],
    *,
    expected_reviewer_app_id: int | None = None,
    expected_controller_app_id: int | None = None,
) -> CheckRunIdentity:
    app = raw.get("app")
    app_id: int | None = None
    app_slug: str | None = None
    if isinstance(app, Mapping):
        if isinstance(app.get("id"), int) and not isinstance(app.get("id"), bool):
            app_id = app["id"]
        if isinstance(app.get("slug"), str):
            app_slug = app["slug"]
    posted_by = _posted_by_from_app_id(
        app_id,
        expected_reviewer_app_id=expected_reviewer_app_id,
        expected_controller_app_id=expected_controller_app_id,
    )
    return CheckRunIdentity(
        name=str(raw.get("name") or ""),
        head_sha=str(raw.get("head_sha") or ""),
        conclusion=str(raw.get("conclusion") or ""),
        app_id=app_id,
        app_slug=app_slug,
        posted_by=posted_by,
    )


def _posted_by_from_app_id(
    app_id: int | None,
    *,
    expected_reviewer_app_id: int | None,
    expected_controller_app_id: int | None,
) -> str:
    if app_id is None:
        return POSTED_BY_WORKER
    if expected_reviewer_app_id is not None and app_id == expected_reviewer_app_id:
        return POSTED_BY_REVIEWER
    if expected_controller_app_id is not None and app_id == expected_controller_app_id:
        return POSTED_BY_CONTROLLER
    return POSTED_BY_FOREIGN


class MergeService:
    def __init__(
        self,
        forge: MergePort,
        *,
        attestation_key: bytes,
        expected_reviewer_app_id: int,
        expected_controller_app_id: int,
    ) -> None:
        self._forge = forge
        self._attestation_key = attestation_key
        self._expected_reviewer_app_id = expected_reviewer_app_id
        self._expected_controller_app_id = expected_controller_app_id

    def rebind(self, forge: MergePort) -> MergeService:
        return MergeService(
            forge,
            attestation_key=self._attestation_key,
            expected_reviewer_app_id=self._expected_reviewer_app_id,
            expected_controller_app_id=self._expected_controller_app_id,
        )

    def consider(self, evidence: MergeEvidence) -> MergeDecision:
        return evaluate_merge_policy(evidence, attestation_key=self._attestation_key)

    def merge_if_eligible(self, number: int) -> MergeDecision:
        evidence = self._load_evidence(number)
        decision = self.consider(evidence)
        if not decision.allowed:
            raise MergeRefused(decision.reason)
        if evidence.base_branch == evidence.protected_branch:
            raise DefaultBranchWriteRefused("never auto-merge the protected default branch")
        self._forge.merge_pull(number, sha=evidence.pr_head_sha, dest=evidence.integration_branch)
        return decision

    def open_promotion_pr(
        self,
        *,
        title: str,
        body: str,
        head: str,
        protected_branch: str,
        key: IdempotencyKey,
    ) -> PromotionRef:
        pull = self._forge.open_pull(
            title=title,
            body=body,
            head=head,
            base=protected_branch,
            draft=True,
            key=key,
        )
        if promotion_pr_auto_merge_allowed():
            raise DefaultBranchWriteRefused(
                "never auto-merge promotion PRs to the protected default branch"
            )
        return PromotionRef(pull=pull, merged=False)

    def _load_evidence(self, number: int) -> MergeEvidence:
        pull = self._forge.get_pull(number)
        checks_raw = self._forge.list_check_runs(pull.head_sha)
        checks = tuple(
            check_identity_from_github(
                item,
                expected_reviewer_app_id=self._expected_reviewer_app_id,
                expected_controller_app_id=self._expected_controller_app_id,
            )
            for item in checks_raw
        )
        comments = tuple(
            _comment_from_github(item) for item in self._forge.list_issue_comments(number)
        )
        labels = tuple(self._forge.list_issue_labels(number))
        attestation = _attestation_from_checks(checks_raw, hmac_key=self._attestation_key)
        policy_source = "head"
        required: tuple[tuple[str, ...], ...] = ()
        freeze = True
        try:
            text = self._forge.file_at_sha(pull.base_sha, POLICY_PATH)
            raw = parse_simple_yaml(text)
            if isinstance(raw, Mapping):
                policy = parse_policy(raw)
                policy_source = "base"
                required = required_commands_from_repository(policy)
                freeze = policy.autonomy.freeze
        except (ForgeError, PolicyError, ValueError):
            policy_source = "head"
            freeze = True
        rerun = False
        if attestation is not None:
            rerun = all(
                command.exit_code == 0 and command.sandbox_fresh for command in attestation.commands
            ) and bool(attestation.commands)
        return MergeEvidence(
            pr_head_sha=pull.head_sha,
            base_branch=pull.base,
            integration_branch=self._forge.integration_branch,
            protected_branch=self._forge.protected_branch,
            labels=labels,
            comments=comments,
            checks=checks,
            review_threads_resolved=self._forge.review_threads_resolved(number),
            ruleset_strict=self._forge.ruleset_strict(),
            expected_reviewer_app_id=self._expected_reviewer_app_id,
            expected_controller_app_id=self._expected_controller_app_id,
            policy_source=policy_source,
            commands_rerun_in_fresh_sandbox=rerun,
            required_commands=required,
            attestation=attestation,
            freeze=freeze,
        )


def _comment_from_github(raw: Mapping[str, object]) -> CommentEvidence:
    user = raw.get("user")
    login = ""
    author_type = "User"
    if isinstance(user, Mapping):
        if isinstance(user.get("login"), str):
            login = user["login"]
        if isinstance(user.get("type"), str):
            author_type = user["type"]
    return CommentEvidence(
        body=str(raw.get("body") or ""),
        author_login=login,
        author_type=author_type,
    )


def _attestation_from_checks(
    checks: Sequence[Mapping[str, object]], *, hmac_key: bytes
) -> RunAttestation | None:
    for raw in checks:
        if raw.get("name") != KRONOS_REVIEW_CHECK_NAME:
            continue
        output = raw.get("output")
        if not isinstance(output, Mapping):
            continue
        text = output.get("text")
        if not isinstance(text, str) or text.strip() == "":
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        try:
            return parse_attestation(payload, hmac_key=hmac_key)
        except AttestationError:
            continue
    return None


__all__ = [
    "CheckRunIdentity",
    "CommentEvidence",
    "MergeDecision",
    "MergeEvidence",
    "MergePort",
    "MergeRefused",
    "MergeService",
    "PromotionRef",
    "evaluate_merge_policy",
    "check_identity_from_github",
    "promotion_pr_auto_merge_allowed",
]
