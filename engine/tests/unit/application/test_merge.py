# SPDX-License-Identifier: AGPL-3.0-or-later
"""MergeService merges integration PRs only after independent review."""

from __future__ import annotations

import pytest
from tests.security.test_reviewer_identity import (
    ATTESTATION_KEY,
    HEAD_SHA,
    _genuine_evidence,
    _reviewer_check,
)

from kronos_engine.application.merge import (
    MergeRefused,
    MergeService,
    promotion_pr_auto_merge_allowed,
)
from kronos_engine.ports.forge import IdempotencyKey, PullRef


class _FakeMerge:
    def __init__(self) -> None:
        self.merged: list[tuple[int, str]] = []
        self.opened: list[dict[str, object]] = []

    def merge_pull(self, number: int, *, sha: str) -> None:
        self.merged.append((number, sha))

    def open_pull(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool,
        key: IdempotencyKey,
    ) -> PullRef:
        self.opened.append(
            {
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": draft,
                "key": key.value,
            }
        )
        return PullRef(
            number=99,
            url="https://github.com/acme/app/pull/99",
            head=head,
            base=base,
            draft=draft,
            created=True,
        )


def test_merge_service_merges_only_genuine_integration_prs() -> None:
    forge = _FakeMerge()
    service = MergeService(forge, attestation_key=ATTESTATION_KEY)
    decision = service.merge_if_eligible(4, _genuine_evidence())
    assert decision.allowed is True
    assert forge.merged == [(4, HEAD_SHA)]


def test_merge_service_does_not_merge_worker_spoof() -> None:
    forge = _FakeMerge()
    service = MergeService(forge, attestation_key=ATTESTATION_KEY)
    with pytest.raises(MergeRefused, match="worker"):
        service.merge_if_eligible(
            4,
            _genuine_evidence(
                checks=(_reviewer_check(app_id=None, posted_by="worker"),),
            ),
        )
    assert forge.merged == []


def test_promotion_pr_is_opened_and_never_merged() -> None:
    forge = _FakeMerge()
    service = MergeService(forge, attestation_key=ATTESTATION_KEY)
    promotion = service.open_promotion_pr(
        title="Promote integration",
        body="Human review required.",
        head="integration",
        protected_branch="main",
        key=IdempotencyKey("promo:acme/app:1"),
    )
    assert promotion.merged is False
    assert promotion.pull.base == "main"
    assert promotion.pull.draft is True
    assert forge.merged == []
    assert promotion_pr_auto_merge_allowed() is False


def test_eligible_review_still_refuses_protected_auto_merge() -> None:
    forge = _FakeMerge()
    service = MergeService(forge, attestation_key=ATTESTATION_KEY)
    with pytest.raises(MergeRefused):
        service.merge_if_eligible(4, _genuine_evidence(base_branch="main"))
    assert forge.merged == []
