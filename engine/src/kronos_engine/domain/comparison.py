# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replay prior decisions against Kronos observe/shadow outcomes. No I/O."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from kronos_engine.domain.policy import ModeWriteRefused, refuse_mode_write

_SECRET_PAYLOAD = re.compile(
    r"ghp_[A-Za-z0-9]|github_pat_|BEGIN [A-Z ]*PRIVATE KEY|Bearer |GH_TOKEN|GITHUB_TOKEN",
    re.IGNORECASE,
)
_ACTION_ALIASES = {
    "create_issue": "create_issue",
    "open_draft_pr": "open_draft_pr",
    "merge": "merge_integration",
    "dispatch": "open_draft_pr",
}


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    task_id: str
    source: str
    action: str
    target_branch: str | None
    identity: str
    payload: str
    wrote: bool
    mode: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonFailure:
    kind: str
    task_id: str
    detail: str


def kronos_shadow_outcome(
    prior: ReplayEvent,
    *,
    mode: str,
    protected_branch: str = "main",
) -> ReplayEvent:
    action = _ACTION_ALIASES.get(prior.action, prior.action)
    wrote = False
    identity = "none"
    try:
        refuse_mode_write(
            mode,
            action,
            target_branch=prior.target_branch,
            protected_branch=protected_branch,
        )
        if prior.identity in {"comment", "label"} and action == "merge_integration":
            identity = prior.identity
        elif prior.target_branch == protected_branch:
            identity = "app_check"
        else:
            identity = "app_check"
    except ModeWriteRefused:
        wrote = False
        identity = "none"
    return ReplayEvent(
        task_id=prior.task_id,
        source="kronos",
        action=prior.action,
        target_branch=prior.target_branch,
        identity=identity,
        payload="",
        wrote=wrote,
        mode=mode,
    )


def evaluate_replay(
    events: Sequence[ReplayEvent],
    *,
    protected_branch: str = "main",
) -> tuple[ComparisonFailure, ...]:
    failures: list[ComparisonFailure] = []
    seen_writes: set[tuple[str, str]] = set()
    for event in events:
        if event.source != "kronos":
            continue
        if event.wrote and event.target_branch == protected_branch:
            failures.append(
                ComparisonFailure(
                    kind="default_branch_write",
                    task_id=event.task_id,
                    detail=f"{event.action} wrote {event.target_branch}",
                )
            )
        if (
            event.action in {"merge", "merge_integration"}
            and event.identity in {"comment", "label"}
            and event.wrote
        ):
            failures.append(
                ComparisonFailure(
                    kind="reviewer_identity_miss",
                    task_id=event.task_id,
                    detail=f"{event.identity} is not merge identity",
                )
            )
        if _SECRET_PAYLOAD.search(event.payload):
            failures.append(
                ComparisonFailure(
                    kind="secret_shaped_payload",
                    task_id=event.task_id,
                    detail="payload contains a secret-shaped token",
                )
            )
        if event.wrote:
            key = (event.task_id, event.action)
            if key in seen_writes:
                failures.append(
                    ComparisonFailure(
                        kind="duplicate_external_write",
                        task_id=event.task_id,
                        detail=f"duplicate {event.action}",
                    )
                )
            seen_writes.add(key)
    return tuple(failures)
