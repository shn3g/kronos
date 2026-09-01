# SPDX-License-Identifier: AGPL-3.0-or-later
"""Goal, task, budget, risk, and claim-order rules. Domain has no I/O."""

from __future__ import annotations

import pytest

from kronos_engine.domain.budgets import (
    BreakerTripped,
    BudgetExceeded,
    BudgetMeter,
    check_budget,
    consume,
    record_failure,
    reset_breaker,
    should_consume,
)
from kronos_engine.domain.entities import GoalId, RepositoryId, TaskId
from kronos_engine.domain.goals import (
    GoalSource,
    GoalSpec,
    GoalState,
    GoalValidationError,
    InvalidTransition,
    transition_goal,
)
from kronos_engine.domain.policy import default_policy
from kronos_engine.domain.risk import apply_planner_risk, apply_planner_size, apply_planner_value
from kronos_engine.domain.tasks import (
    CycleError,
    EvidenceLocator,
    SchemaError,
    TaskGraph,
    TaskKind,
    TaskNode,
    TaskState,
    detect_cycle,
    parse_task_graph,
    transition_task,
)
from kronos_engine.domain.workflow import (
    CLAIM_STEPS,
    ClaimRequiresTaskId,
    EmptyTestCommands,
    MissingWorktree,
    NoTestStop,
    ScheduledSpawnForbidden,
    TddGateError,
    UnresolvedEvidence,
    assert_red_green,
    forbid_unbound_spawn,
    require_evidence,
    require_explicit_task_id,
    require_reproduction_artifact,
    require_test_commands,
    require_worktree_path,
)


def test_goal_requires_repository_criteria_nongoals_budget_risk_and_source() -> None:
    with pytest.raises(GoalValidationError, match="success criteria"):
        GoalSpec(
            repository_id=RepositoryId("repo_a"),
            title="Fix add",
            success_criteria="",
            non_goals="rewrite the parser",
            risk_ceiling="low",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    with pytest.raises(GoalValidationError, match="non-goals"):
        GoalSpec(
            repository_id=RepositoryId("repo_a"),
            title="Fix add",
            success_criteria="add returns a+b",
            non_goals="",
            risk_ceiling="low",
            source=GoalSource.API,
            max_attempts=3,
        )
    with pytest.raises(GoalValidationError, match="schedule"):
        GoalSpec(
            repository_id=RepositoryId("repo_a"),
            title="Fix add",
            success_criteria="add returns a+b",
            non_goals="rewrite the parser",
            risk_ceiling="low",
            source=GoalSource.SCHEDULE,
            max_attempts=3,
        )
    with pytest.raises(GoalValidationError, match="budget"):
        GoalSpec(
            repository_id=RepositoryId("repo_a"),
            title="Fix add",
            success_criteria="add returns a+b",
            non_goals="rewrite the parser",
            risk_ceiling="medium",
            source=GoalSource.CLI,
            max_attempts=0,
        )
    spec = GoalSpec(
        repository_id=RepositoryId("repo_a"),
        title="Fix add",
        success_criteria="add returns a+b",
        non_goals="rewrite the parser",
        risk_ceiling="medium",
        source=GoalSource.CLI,
        max_attempts=3,
    )
    assert spec.source is GoalSource.CLI
    assert spec.max_attempts == 3
    chat = GoalSpec(
        repository_id=RepositoryId("repo_a"),
        title="Fix add",
        success_criteria="add returns a+b",
        non_goals="rewrite the parser",
        risk_ceiling="medium",
        source=GoalSource.CHAT,
        max_attempts=3,
    )
    assert chat.source is GoalSource.CHAT
    assert chat.source.value == "chat"


def test_goal_and_task_reject_invalid_transitions() -> None:
    assert transition_goal(GoalState.DRAFT, GoalState.PLANNED) is GoalState.PLANNED
    with pytest.raises(InvalidTransition):
        transition_goal(GoalState.COMPLETED, GoalState.ACTIVE)
    with pytest.raises(InvalidTransition):
        transition_goal(GoalState.STOPPED, GoalState.DRAFT)
    assert transition_task(TaskState.READY, TaskState.CLAIMED) is TaskState.CLAIMED
    with pytest.raises(InvalidTransition):
        transition_task(TaskState.MERGED, TaskState.RUNNING)


def test_planner_dag_rejects_cycles_and_invalid_schema() -> None:
    with pytest.raises(SchemaError):
        parse_task_graph({"tasks": "nope"})
    cyclic = parse_task_graph(
        {
            "tasks": [
                {
                    "id": "t1",
                    "title": "one",
                    "kind": "implementation",
                    "depends_on": ["t2"],
                    "evidence": [{"path": "pkg/math.py", "line": 1}],
                    "size": "S",
                    "baseline_size": "S",
                    "risk": "low",
                    "scope_paths": ["pkg/math.py"],
                },
                {
                    "id": "t2",
                    "title": "two",
                    "kind": "implementation",
                    "depends_on": ["t1"],
                    "evidence": [{"path": "pkg/math.py", "line": 1}],
                    "size": "S",
                    "baseline_size": "S",
                    "risk": "low",
                    "scope_paths": ["pkg/math.py"],
                },
            ]
        }
    )
    with pytest.raises(CycleError):
        detect_cycle(cyclic)


def test_size_may_rise_one_step_and_never_shrink_risk_only_moves_up() -> None:
    assert apply_planner_size("XS", "M") == "XS_PLUS"
    assert apply_planner_size("S", "XS") == "S"
    assert apply_planner_size("S", "M") == "M"
    assert apply_planner_risk("medium", "low") == "medium"
    assert apply_planner_risk("low", "high") == "high"
    assert apply_planner_value("critical", "cosmetic") == "critical"


def test_claim_requires_task_id_and_scheduled_spawn_is_bound() -> None:
    assert CLAIM_STEPS == ("freeze", "budget", "evidence", "lease", "worktree", "worker")
    with pytest.raises(ClaimRequiresTaskId, match="explicit task id"):
        require_explicit_task_id("")
    with pytest.raises(ClaimRequiresTaskId):
        require_explicit_task_id(None)
    assert require_explicit_task_id("task_1") == "task_1"
    with pytest.raises(ScheduledSpawnForbidden, match="claimed task id"):
        forbid_unbound_spawn(None)
    with pytest.raises(ScheduledSpawnForbidden):
        forbid_unbound_spawn("")
    assert forbid_unbound_spawn("task_1") == "task_1"


def test_dry_run_does_not_consume_unless_shadow_metering() -> None:
    policy = default_policy(integration_branch="integration", protected_branch="main")
    meter = BudgetMeter(
        attempts=0,
        daily_dispatches=0,
        consecutive_failures=0,
        breaker_open=False,
        day="2026-08-31",
    )
    check_budget(meter, policy, task_attempts=0)
    assert should_consume(dry_run=True, shadow_metering=False) is False
    assert consume(meter, dry_run=True, shadow_metering=False) == meter
    shadowed = consume(meter, dry_run=True, shadow_metering=True)
    assert shadowed.attempts == 1
    live = consume(meter, dry_run=False, shadow_metering=False)
    assert live.daily_dispatches == 1


def test_budget_cap_and_breaker_are_deterministic() -> None:
    policy = default_policy(integration_branch="integration", protected_branch="main")
    meter = BudgetMeter(
        attempts=0,
        daily_dispatches=0,
        consecutive_failures=0,
        breaker_open=False,
        day="2026-08-31",
    )
    with pytest.raises(BudgetExceeded, match="attempt"):
        check_budget(meter, policy, task_attempts=3)
    tripped = record_failure(meter, policy.budgets.breaker_failure_limit)
    for _ in range(policy.budgets.breaker_failure_limit - 1):
        tripped = record_failure(tripped, policy.budgets.breaker_failure_limit)
    assert tripped.breaker_open is True
    with pytest.raises(BreakerTripped):
        check_budget(tripped, policy, task_attempts=0)
    cleared = reset_breaker(tripped)
    check_budget(cleared, policy, task_attempts=0)


def test_no_test_implementation_is_a_stop_docs_exemption_passes() -> None:
    with pytest.raises(NoTestStop, match="no-test"):
        require_reproduction_artifact("implementation", ("src/app.py",), None)
    with pytest.raises(NoTestStop, match="no-test"):
        require_reproduction_artifact("implementation", ("notes_repro.md",), None)
    require_reproduction_artifact("docs", ("README.md",), None)
    require_reproduction_artifact("config", ("pyproject.toml",), None)
    require_reproduction_artifact(
        "implementation", ("tests/test_repro.py", "src/app.py"), None
    )
    require_reproduction_artifact("implementation", ("pkg/math_test.py",), None)


def test_empty_evidence_refuses_implementation_docs_may_skip() -> None:
    with pytest.raises(UnresolvedEvidence, match="empty evidence"):
        require_evidence("implementation", (), None)
    require_evidence("docs", (), None)
    require_evidence("config", (), "config")
    require_evidence(
        "implementation",
        (EvidenceLocator(path="pkg/math.py", line=1),),
        None,
    )


def test_accept_requires_worktree_red_green_and_configured_tests() -> None:
    with pytest.raises(MissingWorktree, match="worktree"):
        require_worktree_path(None)
    with pytest.raises(MissingWorktree, match="worktree"):
        require_worktree_path("")
    with pytest.raises(MissingWorktree, match="worktree"):
        require_worktree_path(".")
    assert require_worktree_path("/cache/worktrees/repo/task") == "/cache/worktrees/repo/task"
    with pytest.raises(EmptyTestCommands, match="empty"):
        require_test_commands(())
    require_test_commands(("pytest", "-q"))
    with pytest.raises(TddGateError, match="red"):
        assert_red_green(red_failed=False, green_passed=True)
    with pytest.raises(TddGateError, match="green"):
        assert_red_green(red_failed=True, green_passed=False)
    assert_red_green(red_failed=True, green_passed=True)


def test_task_graph_parse_keeps_evidence_and_ids() -> None:
    graph = parse_task_graph(
        {
            "tasks": [
                {
                    "id": "task_add",
                    "title": "fix add",
                    "kind": "implementation",
                    "depends_on": [],
                    "evidence": [{"path": "pkg/math.py", "line": 1}],
                    "size": "S",
                    "baseline_size": "XS",
                    "risk": "low",
                    "scope_paths": ["pkg/math.py"],
                }
            ]
        }
    )
    assert isinstance(graph, TaskGraph)
    node = graph.nodes[0]
    assert isinstance(node, TaskNode)
    assert node.id == TaskId("task_add")
    assert node.kind is TaskKind.IMPLEMENTATION
    assert node.evidence == (EvidenceLocator(path="pkg/math.py", line=1),)
    assert node.goal_id is None or isinstance(node.goal_id, GoalId)
