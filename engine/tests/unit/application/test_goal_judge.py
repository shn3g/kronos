# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for evidence-based goal completion decisions."""

from __future__ import annotations

from kronos_engine.application.goal_judge import GoalJudge
from kronos_engine.domain.entities import GoalId, RepositoryId, TaskId
from kronos_engine.domain.tasks import TaskKind, TaskRecord, TaskState


def _task(*, artifacts: tuple[str, ...] = ()) -> TaskRecord:
    return TaskRecord(
        id=TaskId("task-1"),
        goal_id=GoalId("goal-1"),
        repository_id=RepositoryId("repo-1"),
        title="Implement goal judge",
        kind=TaskKind.IMPLEMENTATION,
        depends_on=(),
        evidence=(),
        size="S",
        baseline_size="S",
        risk="low",
        scope_paths=(),
        state=TaskState.MERGED,
        artifacts=artifacts,
    )


def test_allows_completion_with_verification_passed_artifact() -> None:
    decision = GoalJudge().decide((_task(artifacts=("verification:gates-passed",)),))

    assert decision.allowed
    assert decision.reason == "goal completion evidence found"


def test_refuses_completion_when_all_tasks_have_empty_evidence() -> None:
    decision = GoalJudge().decide((_task(),))

    assert not decision.allowed
    assert "evidence" in decision.reason


def test_allows_completion_with_passing_gate_exit_code_evidence() -> None:
    decision = GoalJudge().decide((_task(artifacts=("pytest: exit code 0",)),))

    assert decision.allowed
    assert decision.reason == "goal completion evidence found"


def test_refuses_completion_when_artifact_is_only_an_existing_path(
    tmp_path,
) -> None:
    from dataclasses import replace

    existing = tmp_path / "src" / "math.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    task = replace(
        _task(artifacts=("src/math.py",)),
        worktree_path=str(tmp_path),
    )

    decision = GoalJudge().decide((task,))

    assert not decision.allowed
    assert "evidence" in decision.reason
