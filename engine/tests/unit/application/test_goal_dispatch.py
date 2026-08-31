# SPDX-License-Identifier: AGPL-3.0-or-later
"""Claim order, fence, breaker, spawn, and TDD accept. Application uses ports."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from tests.e2e.test_goal_to_integration_pr import GoalHarness, ScriptedPlanner

from kronos_engine.application.dispatch import ExecuteResult
from kronos_engine.domain.entities import TaskId
from kronos_engine.domain.goals import (
    GoalSource,
    GoalSpec,
    GoalState,
    GoalValidationError,
    InvalidTransition,
)
from kronos_engine.domain.tasks import EvidenceLocator, TaskState
from kronos_engine.domain.workflow import ScheduledSpawnForbidden, UnresolvedEvidence
from kronos_engine.state.scheduler import GoalScheduler


def test_empty_evidence_refuses_implementation_claim(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    task = harness.store.get_task(harness.task_id)
    harness.store.save_task(replace(task, evidence=()))
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is False
    assert claimed.failed_step == "evidence"
    assert "empty evidence" in claimed.reason


def test_unmerged_dependency_blocks_claim(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    parent_id = TaskId("task_parent")
    task = harness.store.get_task(harness.task_id)
    parent = replace(
        task,
        id=parent_id,
        title="parent",
        state=TaskState.READY,
        depends_on=(),
        evidence=(EvidenceLocator(path="pkg/math.py", line=1),),
    )
    harness.store.save_task(parent)
    harness.store.save_task(replace(task, depends_on=(parent_id,)))
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is False
    assert claimed.failed_step == "evidence"
    assert "not merged" in claimed.reason


def test_freeze_still_consumes_zero_and_lock_held_is_lease_result(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    harness.set_freeze(True)
    refused = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert refused.ok is False
    assert refused.failed_step == "freeze"
    assert harness.store.task_attempts(harness.task_id) == 0
    harness.set_freeze(False)
    area = "pkg/math.py"
    key = f"{harness.repo_id.value}:area:{area}"
    harness.leases.acquire(key, "other-holder", timedelta(hours=2), now=harness.now)
    locked = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert locked.ok is False
    assert locked.failed_step == "lease"
    assert locked.budget_consumed is True


def test_execute_asserts_fence_and_breaker_opens_after_failures(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "model_outage")
    harness.setup_goal()
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is True
    assert claimed.ok is True
    assert claimed.lease is not None
    stale_lease = replace(claimed.lease, fence_token=claimed.lease.fence_token + 9)
    stale = replace(claimed, lease=stale_lease)
    fenced = harness.dispatch.execute(stale)
    assert fenced.ok is False
    assert fenced.error is not None
    assert "fence" in fenced.error.lower() or "stale" in fenced.error.lower()

    live = harness.dispatch.execute(claimed)
    assert live.ok is False
    harness.recovery.pause_or_stop(harness.task_id, live.error or "outage", live.error or "outage")
    meter = harness.store.budget_meter(harness.repo_id, harness.now.date().isoformat())
    limit = harness.repos.get(harness.repo_id).policy.budgets.breaker_failure_limit
    for _ in range(limit):
        harness.dispatch.record_run_failure(harness.task_id)
    tripped = harness.store.budget_meter(harness.repo_id, harness.now.date().isoformat())
    assert tripped.breaker_open is True
    assert tripped.consecutive_failures >= limit
    _ = meter


def test_accept_refuses_missing_worktree_and_empty_test_commands(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    executed = harness.dispatch.execute(claimed, phase="red")
    task = harness.store.get_task(harness.task_id)
    harness.store.save_task(replace(task, worktree_path=None))
    missing = harness.verification.accept(
        harness.task_id,
        executed,
        red_failed=True,
    )
    assert missing.ok is False
    assert "worktree" in missing.reason.lower()

    current = harness.store.get_task(harness.task_id)
    harness.store.save_task(replace(current, worktree_path=str(claimed.worktree)))
    record = harness.repos.get(harness.repo_id)
    payload = record.policy
    from kronos_engine.domain.policy import parse_policy, policy_to_dict

    raw = policy_to_dict(payload)
    raw["commands"] = {"setup": [], "test": [], "lint": [], "build": []}
    from kronos_engine.state.repositories import SqliteRepositoryRegistry

    SqliteRepositoryRegistry(harness.conn).save(replace(record, policy=parse_policy(raw)))
    empty = harness.verification.accept(
        harness.task_id,
        ExecuteResult(ok=True, artifacts=("tests/test_repro.py",), error=None, status="succeeded"),
        red_failed=True,
    )
    assert empty.ok is False
    assert "empty" in empty.reason.lower()


def test_spawn_requires_claimed_task_and_live_fence(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    with pytest.raises(ScheduledSpawnForbidden):
        harness.scheduler.spawn(harness.task_id)
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is True
    assert harness.scheduler.spawn(harness.task_id) == harness.task_id
    task = harness.store.get_task(harness.task_id)
    harness.store.save_task(replace(task, fence_token=None))
    with pytest.raises(ScheduledSpawnForbidden):
        harness.scheduler.spawn(harness.task_id)


def test_github_ingest_refuses_placeholder_nongoals(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    with pytest.raises(GoalValidationError):
        harness.scheduler.ingest_github_issue(
            repository_id=harness.repo_id,
            title="From GitHub",
            body="do the thing",
            non_goals="",
            risk_ceiling="medium",
            max_attempts=3,
        )


def test_plan_refuses_stopped_goals_and_empty_evidence_graph(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    goal = harness.store.get_goal(harness.goal.id)
    harness.store.save_goal(replace(goal, state=GoalState.STOPPED))
    with pytest.raises(InvalidTransition):
        harness.planning.plan(harness.goal.id)

    class EmptyEvidencePlanner:
        def plan(self, goal: object) -> dict[str, object]:
            _ = goal
            return {
                "tasks": [
                    {
                        "id": "task_empty",
                        "title": "empty",
                        "kind": "implementation",
                        "depends_on": [],
                        "evidence": [],
                        "size": "S",
                        "baseline_size": "XS",
                        "risk": "low",
                        "scope_paths": ["pkg/math.py"],
                    }
                ]
            }

    fresh = GoalHarness(tmp_path / "empty", "happy")
    fresh.setup_goal()
    fresh.planning = type(fresh.planning)(
        fresh.store, fresh.repos, fresh.recorder, EmptyEvidencePlanner()
    )
    with pytest.raises(UnresolvedEvidence):
        fresh.planning.plan(fresh.goal.id)


def test_replan_refuses_when_task_claimed(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    task = harness.store.get_task(harness.task_id)
    harness.store.save_task(replace(task, state=TaskState.CLAIMED))
    with pytest.raises(InvalidTransition, match="claimed"):
        harness.planning.plan(harness.goal.id)


def test_tick_surfaces_draft_plan_failure(tmp_path: Path) -> None:
    from kronos_engine.application.planning import PlanningService
    from kronos_engine.domain.tasks import SchemaError
    from kronos_engine.indexing.service import IndexingService

    harness = GoalHarness(tmp_path, "happy")
    record = harness.repos.enrol(str(harness.repo_root))
    harness.repo_id = record.id
    IndexingService(harness.paths).rebuild(record.id.value, harness.repo_root, record.policy)
    harness.goals.create(
        GoalSpec(
            repository_id=record.id,
            title="Draft only",
            success_criteria="add(1, 1) == 2",
            non_goals="do not rewrite packaging",
            risk_ceiling="medium",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )

    class FailingPlanner:
        def plan(self, goal: object) -> dict[str, object]:
            _ = goal
            raise SchemaError("index has no source path for evidence")

    harness.planning = PlanningService(
        harness.store, harness.repos, harness.recorder, FailingPlanner()
    )
    harness.engine = type(harness.engine)(
        harness.store,
        harness.planning,
        harness.dispatch,
        harness.verification,
        harness.recovery,
        harness.merge,
        harness.scheduler,
        clock=lambda: harness.now,
    )
    result = harness.engine.tick()
    assert result.ok is False
    assert result.status == "plan_failed"
    assert "index has no source path" in result.reason


def test_scheduler_is_goal_scheduler() -> None:
    assert GoalScheduler.__name__ == "GoalScheduler"
    assert ScriptedPlanner.__name__ == "ScriptedPlanner"

