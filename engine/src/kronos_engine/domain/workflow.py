# SPDX-License-Identifier: AGPL-3.0-or-later
"""Claim order, spawn binding, and red-green artifact rules. No I/O."""

from __future__ import annotations

from collections.abc import Sequence

CLAIM_STEPS: tuple[str, ...] = ("freeze", "budget", "evidence", "lease", "worktree", "worker")


class ClaimRefused(RuntimeError):
    """Raised when a claim step refuses the task."""

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"{step}: {reason}")


class ClaimRequiresTaskId(ValueError):
    """Raised when claim or spawn is missing an explicit task id."""


class ScheduledSpawnForbidden(ValueError):
    """Raised when a schedule would spawn a worker without a claimed task id."""


class NoTestStop(RuntimeError):
    """Raised when implementation completed without a reproduction test."""


class UnresolvedEvidence(RuntimeError):
    """Raised when evidence is not present in the indexed commit."""


def require_explicit_task_id(task_id: str | None) -> str:
    if task_id is None or str(task_id).strip() == "":
        raise ClaimRequiresTaskId("claim requires an explicit task id")
    return str(task_id)


def forbid_unbound_spawn(task_id: str | None) -> str:
    if task_id is None or str(task_id).strip() == "":
        raise ScheduledSpawnForbidden("scheduled spawn without a claimed task id is forbidden")
    return str(task_id)


def require_reproduction_artifact(
    kind: str, artifacts: Sequence[str], exemption: str | None
) -> None:
    if kind in {"docs", "config"} and exemption in {"docs", "config"}:
        return
    if not any(_is_test_artifact(item) for item in artifacts):
        raise NoTestStop("no-test implementation is a stop, not a merge")


def _is_test_artifact(path: str) -> bool:
    posix = path.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    lowered = posix.lower()
    return (
        "/tests/" in f"/{posix}/"
        or posix.startswith("tests/")
        or name.startswith("test_")
        or name.endswith("_test.py")
        or "repro" in lowered
        or "reproduction" in lowered
    )
