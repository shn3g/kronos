# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replay prior dispatch/merge fixtures against Kronos observe/shadow outcomes."""

from __future__ import annotations

from kronos_engine.domain.comparison import (
    ReplayEvent,
    evaluate_replay,
    kronos_shadow_outcome,
)


def _prior(
    *,
    task_id: str = "issue-12",
    action: str = "merge",
    target_branch: str = "main-openclaw",
    identity: str = "app_check",
    payload: str = "ok",
    wrote: bool = True,
) -> ReplayEvent:
    return ReplayEvent(
        task_id=task_id,
        source="prior",
        action=action,
        target_branch=target_branch,
        identity=identity,
        payload=payload,
        wrote=wrote,
        mode=None,
    )


def test_shadow_refuses_writes_that_prior_would_perform() -> None:
    dispatch = _prior(action="open_draft_pr", identity="none")
    merge_main = _prior(action="merge", target_branch="main", identity="comment")
    shadowed = (
        kronos_shadow_outcome(dispatch, mode="shadow"),
        kronos_shadow_outcome(merge_main, mode="observe"),
    )
    assert all(item.wrote is False for item in shadowed)
    assert evaluate_replay((dispatch, merge_main, *shadowed), protected_branch="main") == ()


def test_harness_hard_fails_default_branch_write() -> None:
    event = ReplayEvent(
        task_id="issue-1",
        source="kronos",
        action="merge",
        target_branch="main",
        identity="app_check",
        payload="ok",
        wrote=True,
        mode="merge_integration",
    )
    failures = evaluate_replay((event,), protected_branch="main")
    assert any(item.kind == "default_branch_write" for item in failures)


def test_harness_hard_fails_comment_identity() -> None:
    event = ReplayEvent(
        task_id="issue-2",
        source="kronos",
        action="merge",
        target_branch="main-openclaw",
        identity="comment",
        payload="<!-- verdict -->",
        wrote=True,
        mode="merge_integration",
    )
    failures = evaluate_replay((event,), protected_branch="main")
    assert any(item.kind == "reviewer_identity_miss" for item in failures)


def test_harness_hard_fails_label_identity() -> None:
    event = ReplayEvent(
        task_id="issue-2b",
        source="kronos",
        action="merge",
        target_branch="main-openclaw",
        identity="label",
        payload="security-reviewed",
        wrote=True,
        mode="merge_integration",
    )
    failures = evaluate_replay((event,), protected_branch="main")
    assert any(item.kind == "reviewer_identity_miss" for item in failures)


def test_harness_hard_fails_duplicate_external_writes() -> None:
    first = ReplayEvent(
        task_id="issue-3",
        source="kronos",
        action="open_draft_pr",
        target_branch="main-openclaw",
        identity="none",
        payload="pr",
        wrote=True,
        mode="write_draft_prs",
    )
    duplicate = ReplayEvent(
        task_id="issue-3",
        source="kronos",
        action="open_draft_pr",
        target_branch="main-openclaw",
        identity="none",
        payload="pr",
        wrote=True,
        mode="write_draft_prs",
    )
    failures = evaluate_replay((first, duplicate), protected_branch="main")
    assert any(item.kind == "duplicate_external_write" for item in failures)


def test_harness_hard_fails_secret_shaped_payload() -> None:
    event = ReplayEvent(
        task_id="issue-4",
        source="kronos",
        action="open_draft_pr",
        target_branch="main-openclaw",
        identity="none",
        payload="Authorization: Bearer ghp_abcdefghijklmnopqrstuvwx",
        wrote=False,
        mode="shadow",
    )
    failures = evaluate_replay((event,), protected_branch="main")
    assert any(item.kind == "secret_shaped_payload" for item in failures)
