# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staged modes refuse GitHub writes; models cannot raise the mode."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from tests.e2e.test_goal_to_integration_pr import (
    POLICY_OVERRIDE,
    GoalHarness,
    ScriptedPlanner,
)

from kronos_engine.application.planning import PlanningService
from kronos_engine.domain.goals import GoalSource, GoalSpec
from kronos_engine.domain.policy import ModeWriteRefused, parse_policy, policy_to_dict
from kronos_engine.domain.tasks import SchemaError
from kronos_engine.state.repositories import SqliteRepositoryRegistry


def _set_mode(harness: GoalHarness, mode: str) -> None:
    record = harness.repos.get(harness.repo_id)
    payload = policy_to_dict(record.policy)
    autonomy = dict(payload["autonomy"])  # type: ignore[arg-type]
    autonomy["mode"] = mode
    autonomy["freeze"] = False
    payload["autonomy"] = autonomy
    updated = replace(record, policy=parse_policy(payload))
    SqliteRepositoryRegistry(harness.conn).save(updated)


def test_observe_and_shadow_do_not_open_prs_or_merge(tmp_path: Path) -> None:
    for mode in ("observe", "shadow"):
        harness = GoalHarness(tmp_path / mode, "happy")
        harness.setup_goal()
        _set_mode(harness, mode)
        result = harness.engine.advance(harness.task_id, holder_id="worker-1")
        kinds = harness.fixture.logical_action_kinds()
        assert "open_draft_pr" not in kinds
        assert "merge_pull" not in kinds
        assert "create_issue" not in kinds
        assert result.pr_url is None
        assert "open_draft_pr" in result.reason or mode in result.reason


def test_write_draft_prs_opens_draft_but_does_not_merge(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    _set_mode(harness, "write_draft_prs")
    result = harness.engine.advance(harness.task_id, holder_id="worker-1")
    kinds = harness.fixture.logical_action_kinds()
    assert "open_draft_pr" in kinds
    assert "merge_pull" not in kinds
    assert result.pr_url is not None


def test_merge_integration_still_refuses_default_branch(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    _set_mode(harness, "merge_integration")
    record = harness.repos.get(harness.repo_id)
    payload = policy_to_dict(record.policy)
    payload["branches"] = {"integration": "integration", "protected": "main"}
    SqliteRepositoryRegistry(harness.conn).save(replace(record, policy=parse_policy(payload)))
    with pytest.raises(ModeWriteRefused, match="protected default branch"):
        from kronos_engine.domain.policy import refuse_mode_write

        refuse_mode_write(
            "merge_integration",
            "merge_integration",
            target_branch="main",
            protected_branch="main",
        )


def test_multi_task_graphs_are_refused_below_multi_task_mode(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    record = harness.repos.enrol(
        str(harness.repo_root),
        {
            **POLICY_OVERRIDE,
            "autonomy": {
                "freeze": False,
                "invent_issues": False,
                "refill_enabled": False,
                "mode": "merge_integration",
            },
            "wip": {"ready": 8, "running": 8},
        },
    )
    harness.repo_id = record.id
    goal = harness.goals.create(
        GoalSpec(
            repository_id=record.id,
            title="Fix add",
            success_criteria="add(1, 1) == 2",
            non_goals="do not rewrite packaging",
            risk_ceiling="medium",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )

    class TwoTaskPlanner:
        def plan(self, goal: object) -> dict[str, object]:
            _ = goal
            base = ScriptedPlanner().plan(goal)
            tasks = list(base["tasks"])  # type: ignore[arg-type]
            extra = dict(tasks[0])  # type: ignore[arg-type]
            extra["id"] = "task_add_two"
            extra["title"] = "second slice"
            extra["scope_paths"] = ["pkg/__init__.py"]
            extra["evidence"] = [{"path": "pkg/__init__.py", "line": 1}]
            tasks.append(extra)
            return {"tasks": tasks}

    planning = PlanningService(harness.store, harness.repos, harness.recorder, TwoTaskPlanner())
    with pytest.raises((ModeWriteRefused, SchemaError), match="multi_task"):
        planning.plan(goal.id)
