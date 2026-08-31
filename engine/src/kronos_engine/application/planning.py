# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic checks on planner DAGs. Application uses ports, not SQL."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.domain.entities import GoalId
from kronos_engine.domain.goals import GoalRecord, GoalState
from kronos_engine.domain.policy import RISK_STEPS
from kronos_engine.domain.risk import apply_planner_risk
from kronos_engine.domain.tasks import (
    SchemaError,
    TaskGraph,
    TaskNode,
    TaskRecord,
    TaskState,
    WipExceeded,
    assert_scope_unlocked,
    detect_cycle,
    parse_task_graph,
)
from kronos_engine.state.goals import SqliteGoalStore


class Planner(Protocol):
    def plan(self, goal: object) -> Mapping[str, object]: ...


class PlanningService:
    def __init__(
        self,
        store: SqliteGoalStore,
        repos: RepositoryService,
        recorder: Recorder,
        planner: Planner,
    ) -> None:
        self._store = store
        self._repos = repos
        self._recorder = recorder
        self._planner = planner

    def plan(self, goal_id: GoalId) -> TaskGraph:
        goal = self._store.get_goal(goal_id)
        repo = self._repos.get(goal.repository_id)
        graph = parse_task_graph(self._planner.plan(goal))
        detect_cycle(graph)
        ready = self._store.count_wip(repo.id, (TaskState.READY, TaskState.PROPOSED))
        if ready + len(graph.nodes) > repo.policy.wip.ready:
            raise WipExceeded("ready WIP cap would be exceeded")
        clamped: list[TaskNode] = []
        for node in graph.nodes:
            assert_scope_unlocked(node.scope_paths, repo.policy.paths.locked_prefixes)
            risk = apply_planner_risk(repo.policy.risk.floor, node.risk)
            if _step(risk) > _step(goal.risk_ceiling):
                raise SchemaError("task risk exceeds goal risk ceiling")
            clamped.append(
                TaskNode(
                    id=node.id,
                    title=node.title,
                    kind=node.kind,
                    depends_on=node.depends_on,
                    evidence=node.evidence,
                    size=node.size,
                    baseline_size=node.baseline_size,
                    risk=risk,
                    scope_paths=node.scope_paths,
                    goal_id=goal.id,
                    exemption=node.exemption,
                )
            )
        bound = TaskGraph(nodes=tuple(clamped))
        for node in bound.nodes:
            self._store.save_task(
                TaskRecord(
                    id=node.id,
                    goal_id=goal.id,
                    repository_id=goal.repository_id,
                    title=node.title,
                    kind=node.kind,
                    depends_on=node.depends_on,
                    evidence=node.evidence,
                    size=node.size,
                    baseline_size=node.baseline_size,
                    risk=node.risk,
                    scope_paths=node.scope_paths,
                    state=TaskState.READY,
                    exemption=node.exemption,
                )
            )
        if goal.state is GoalState.DRAFT:
            planned = _with_state(goal, GoalState.PLANNED)
            self._store.save_goal(planned)
            self._recorder.emit(
                "goal.transitioned",
                {
                    "goal_id": goal.id.value,
                    "from": goal.state.value,
                    "to": GoalState.PLANNED.value,
                },
            )
        self._recorder.emit(
            "task.planned",
            {
                "goal_id": goal.id.value,
                "task_ids": [node.id.value for node in bound.nodes],
            },
        )
        return bound


def _with_state(goal: GoalRecord, state: GoalState) -> GoalRecord:
    return GoalRecord(
        id=goal.id,
        repository_id=goal.repository_id,
        title=goal.title,
        success_criteria=goal.success_criteria,
        non_goals=goal.non_goals,
        risk_ceiling=goal.risk_ceiling,
        source=goal.source,
        state=state,
        schedule=goal.schedule,
        stop_reason=goal.stop_reason,
        created_at=goal.created_at,
    )


def _step(value: str) -> int:
    return RISK_STEPS.index(value)
