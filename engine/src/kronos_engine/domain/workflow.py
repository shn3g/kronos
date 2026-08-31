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


class MissingWorktree(RuntimeError):
    """Raised when accept or gates run without a stored worktree path."""


class EmptyTestCommands(RuntimeError):
    """Raised when configured test commands are empty."""


class TddGateError(RuntimeError):
    """Raised when accept is not a failing test followed by a passing test."""


def require_explicit_task_id(task_id: str | None) -> str:
    if task_id is None or str(task_id).strip() == "":
        raise ClaimRequiresTaskId("claim requires an explicit task id")
    return str(task_id)


def forbid_unbound_spawn(task_id: str | None) -> str:
    if task_id is None or str(task_id).strip() == "":
        raise ScheduledSpawnForbidden("scheduled spawn without a claimed task id is forbidden")
    return str(task_id)


def require_evidence(kind: str, locators: Sequence[object], exemption: str | None) -> None:
    _ = exemption
    if kind in {"docs", "config"}:
        return
    if len(locators) == 0:
        raise UnresolvedEvidence("empty evidence refuses implementation")


def require_reproduction_artifact(
    kind: str, artifacts: Sequence[str], exemption: str | None
) -> None:
    _ = exemption
    if kind in {"docs", "config"}:
        return
    if not any(_is_test_artifact(item) for item in artifacts):
        raise NoTestStop("no-test implementation is a stop, not a merge")


def require_worktree_path(path: str | None) -> str:
    if path is None or str(path).strip() == "" or str(path).strip() == ".":
        raise MissingWorktree("worktree_path is required")
    return str(path)


def require_test_commands(commands: Sequence[str]) -> None:
    if not commands:
        raise EmptyTestCommands("configured test commands are empty")


def assert_red_green(*, red_failed: bool, green_passed: bool) -> None:
    if not red_failed:
        raise TddGateError("TDD red required before accept")
    if not green_passed:
        raise TddGateError("TDD green required to accept")


def lease_resource_key(repository_id: str, scope_paths: Sequence[str], task_id: str) -> str:
    area = scope_paths[0] if scope_paths else task_id
    return f"{repository_id}:area:{area}"


def _is_test_artifact(path: str) -> bool:
    posix = path.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{posix}/"
        or posix.startswith("tests/")
        or name.endswith("_test.py")
    )
