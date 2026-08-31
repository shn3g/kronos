# SPDX-License-Identifier: AGPL-3.0-or-later
"""MergeService merges integration PRs only after independent review."""

from __future__ import annotations

from tests.security.test_reviewer_identity import (
    ATTESTATION_KEY,
    CONTROLLER_APP_ID,
    REVIEWER_APP_ID,
    _genuine_evidence,
    _reviewer_check,
)

from kronos_engine.application.merge import (
    MergeService,
    promotion_pr_auto_merge_allowed,
)
from kronos_engine.ports.forge import IdempotencyKey, PullRef


class _FakeMerge:
    integration_branch = "integration"
    protected_branch = "main"

    def __init__(self) -> None:
        self.merged: list[tuple[int, str]] = []
        self.opened: list[dict[str, object]] = []

    def merge_pull(self, number: int, *, sha: str, dest: str | None = None) -> None:
        _ = dest
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

    def get_pull(self, number: int) -> PullRef:
        raise NotImplementedError

    def list_check_runs(self, sha: str) -> tuple[dict[str, object], ...]:
        raise NotImplementedError

    def list_issue_comments(self, number: int) -> tuple[dict[str, object], ...]:
        raise NotImplementedError

    def list_issue_labels(self, number: int) -> tuple[str, ...]:
        raise NotImplementedError

    def ruleset_strict(self) -> bool:
        raise NotImplementedError

    def review_threads_resolved(self, number: int) -> bool:
        raise NotImplementedError

    def file_at_sha(self, sha: str, path: str) -> str:
        raise NotImplementedError


def _service(forge: _FakeMerge) -> MergeService:
    return MergeService(
        forge,
        attestation_key=ATTESTATION_KEY,
        expected_reviewer_app_id=REVIEWER_APP_ID,
        expected_controller_app_id=CONTROLLER_APP_ID,
    )


def test_consider_allows_genuine_and_refuses_worker() -> None:
    forge = _FakeMerge()
    service = _service(forge)
    assert service.consider(_genuine_evidence()).allowed is True
    worker = service.consider(
        _genuine_evidence(checks=(_reviewer_check(app_id=None, posted_by="worker"),))
    )
    assert worker.allowed is False
    assert forge.merged == []


def test_promotion_pr_is_opened_and_never_merged() -> None:
    forge = _FakeMerge()
    service = _service(forge)
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


def test_consider_refuses_protected_default() -> None:
    forge = _FakeMerge()
    service = _service(forge)
    decision = service.consider(_genuine_evidence(base_branch="main"))
    assert decision.allowed is False
    assert forge.merged == []
