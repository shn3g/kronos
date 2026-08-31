# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration merge after independent review. Promotion PRs are never auto-merged."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from kronos_engine.domain.attestations import (
    CheckRunIdentity,
    CommentEvidence,
    MergeDecision,
    MergeEvidence,
    evaluate_merge_policy,
)
from kronos_engine.ports.forge import DefaultBranchWriteRefused, IdempotencyKey, PullRef


class MergeRefused(RuntimeError):
    """Raised when merge policy refuses an integration merge."""


class MergePort(Protocol):
    def merge_pull(self, number: int, *, sha: str) -> None: ...

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


@dataclass(frozen=True, slots=True)
class PromotionRef:
    pull: PullRef
    merged: bool


def promotion_pr_auto_merge_allowed() -> bool:
    return False


def check_identity_from_github(raw: Mapping[str, object]) -> CheckRunIdentity:
    app = raw.get("app")
    app_id: int | None = None
    app_slug: str | None = None
    if isinstance(app, Mapping):
        if isinstance(app.get("id"), int) and not isinstance(app.get("id"), bool):
            app_id = app["id"]
        if isinstance(app.get("slug"), str):
            app_slug = app["slug"]
    posted_by = raw.get("posted_by")
    if not isinstance(posted_by, str) or posted_by == "":
        posted_by = "worker" if app_id is None else "foreign"
    return CheckRunIdentity(
        name=str(raw.get("name") or ""),
        head_sha=str(raw.get("head_sha") or ""),
        conclusion=str(raw.get("conclusion") or ""),
        app_id=app_id,
        app_slug=app_slug,
        posted_by=posted_by,
    )


class MergeService:
    def __init__(self, forge: MergePort, *, attestation_key: bytes) -> None:
        self._forge = forge
        self._attestation_key = attestation_key

    def consider(self, evidence: MergeEvidence) -> MergeDecision:
        return evaluate_merge_policy(evidence, attestation_key=self._attestation_key)

    def merge_if_eligible(self, number: int, evidence: MergeEvidence) -> MergeDecision:
        decision = self.consider(evidence)
        if not decision.allowed:
            raise MergeRefused(decision.reason)
        if evidence.base_branch == evidence.protected_branch:
            raise DefaultBranchWriteRefused(
                "never auto-merge the protected default branch"
            )
        self._forge.merge_pull(number, sha=evidence.pr_head_sha)
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
