# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic checks on planner DAGs. Application uses ports, not SQL."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from kronos_engine.adapters.models.openai_compatible import HttpTransport, OpenAICompatibleProvider
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.domain.budgets import check_budget
from kronos_engine.domain.entities import GoalId
from kronos_engine.domain.goals import GoalRecord, GoalState, InvalidTransition, transition_goal
from kronos_engine.domain.models import CostCeilingExceeded, assert_cost_allowed
from kronos_engine.domain.policy import RISK_STEPS, refuse_mode_write
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
from kronos_engine.domain.workflow import require_evidence
from kronos_engine.ports.model_provider import CompletionRequest
from kronos_engine.ports.model_registry import ModelRegistry
from kronos_engine.ports.secrets import ScopedSecret, SecretExpiredError, SecretStore
from kronos_engine.state.goals import SqliteGoalStore


class Planner(Protocol):
    def plan(self, goal: object) -> Mapping[str, object]: ...


_IN_FLIGHT_TASK_STATES = frozenset(
    {
        TaskState.CLAIMED,
        TaskState.RUNNING,
        TaskState.AWAITING_GATES,
        TaskState.AWAITING_REVIEW,
        TaskState.MERGED,
    }
)


class PlanningService:
    def __init__(
        self,
        store: SqliteGoalStore,
        repos: RepositoryService,
        recorder: Recorder,
        planner: Planner,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._repos = repos
        self._recorder = recorder
        self._planner = planner
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def plan(self, goal_id: GoalId) -> TaskGraph:
        goal = self._store.get_goal(goal_id)
        if goal.state not in {GoalState.DRAFT, GoalState.PLANNED}:
            raise InvalidTransition(f"cannot plan goal from {goal.state}")
        for task in self._store.list_tasks(goal_id):
            if task.state in _IN_FLIGHT_TASK_STATES:
                raise InvalidTransition(
                    f"cannot re-plan goal while task {task.id.value} is {task.state.value}"
                )
        repo = self._repos.get(goal.repository_id)
        meter = self._store.budget_meter(repo.id, self._clock().date().isoformat())
        check_budget(meter, repo.policy, task_attempts=0)
        graph = parse_task_graph(self._planner.plan(goal))
        detect_cycle(graph)
        if len(graph.nodes) > 1:
            refuse_mode_write(repo.policy.autonomy.mode, "multi_task")
        ready = self._store.count_wip(repo.id, (TaskState.READY, TaskState.PROPOSED))
        if ready + len(graph.nodes) > repo.policy.wip.ready:
            raise WipExceeded("ready WIP cap would be exceeded")
        clamped: list[TaskNode] = []
        for node in graph.nodes:
            require_evidence(node.kind.value, node.evidence, node.exemption)
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
            planned = replace(goal, state=transition_goal(goal.state, GoalState.PLANNED))
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
        self._recorder.emit(
            "policy.evaluated",
            {"goal_id": goal.id.value, "task_count": len(bound.nodes)},
        )
        return bound


class IndexedPlanner:
    """Deterministic one-task plan from the first indexed source path."""

    def __init__(self, indexer: object) -> None:
        self._indexer = indexer

    def plan(self, goal: object) -> dict[str, object]:
        assert isinstance(goal, GoalRecord)
        chunks = getattr(self._indexer, "list_chunks")(goal.repository_id.value)
        source = None
        for chunk in chunks:
            path = str(getattr(chunk, "path", "")).replace("\\", "/")
            if path and "/tests/" not in f"/{path}/" and not path.startswith("tests/"):
                source = chunk
                break
        if source is None:
            raise SchemaError("index has no source path for evidence")
        path = str(source.path)
        line = int(getattr(source, "start_line", 1) or 1)
        return {
            "tasks": [
                {
                    "id": f"task_{goal.id.value}",
                    "title": goal.title,
                    "kind": "implementation",
                    "depends_on": [],
                    "evidence": [{"path": path, "line": line}],
                    "size": "S",
                    "baseline_size": "S",
                    "risk": "low",
                    "scope_paths": [path],
                }
            ]
        }


_PLANNER_SYSTEM = (
    "Return only a JSON object with this shape: "
    '{"tasks":[{"id":"","title":"","kind":"implementation","depends_on":[],'
    '"evidence":[{"path":"","line":1}],"size":"S","baseline_size":"S",'
    '"risk":"low","scope_paths":[""]}]}. No markdown.'
)
_SECRET_TTL_SECONDS = 60


class LlmPlanner:
    """Planner-role completion with IndexedPlanner as the deterministic fallback."""

    def __init__(
        self,
        registry: ModelRegistry,
        secrets: SecretStore,
        fallback: Planner,
        *,
        complete: Callable[..., object] | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self._registry = registry
        self._secrets = secrets
        self._fallback = fallback
        self._complete = complete
        self._transport = transport

    def plan(self, goal: object) -> Mapping[str, object]:
        planned = self._llm_plan(goal)
        if planned is None:
            result = self._fallback.plan(goal)
            return dict(result) if not isinstance(result, dict) else result
        return planned

    def _llm_plan(self, goal: object) -> dict[str, object] | None:
        if not isinstance(goal, GoalRecord):
            return None
        assignments = self._registry.load_assignments()
        profile_id = assignments.planner
        if not profile_id:
            return None
        profiles = {item.id: item for item in self._registry.list_profiles()}
        profile = profiles.get(profile_id)
        if profile is None:
            return None
        providers = {item.id: item for item in self._registry.list_providers()}
        provider = providers.get(profile.provider_id)
        if provider is None or not provider.base_url:
            return None
        raw = self._secrets.get(provider.secret_ref)
        secret = ScopedSecret(value=raw, ttl_seconds=_SECRET_TTL_SECONDS) if raw else None
        prompt = (
            f"Goal: {goal.title}\n"
            f"Success criteria: {goal.success_criteria}\n"
            f"Non-goals: {goal.non_goals}\n"
            f"Risk ceiling: {goal.risk_ceiling}\n"
            "Emit a single-task JSON plan with evidence and scope_paths."
        )
        request = CompletionRequest(
            profile=profile,
            prompt=prompt,
            messages=(
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": prompt},
            ),
        )
        try:
            billed = provider.billed or profile.billed
            assert_cost_allowed(profile.limits, estimated_cost=0.0, billed=billed)
            if self._complete is not None:
                result = self._complete(request, secret)
            else:
                adapter = OpenAICompatibleProvider(
                    base_url=provider.base_url,
                    billed=provider.billed,
                    transport=self._transport,
                )
                result = adapter.complete(request, secret)
            text = getattr(result, "text", "")
            if not isinstance(text, str):
                return None
            parsed: object = json.loads(text)
            parse_task_graph(parsed)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except (
            CostCeilingExceeded,
            SchemaError,
            json.JSONDecodeError,
            RuntimeError,
            ValueError,
            TypeError,
            SecretExpiredError,
            OSError,
        ):
            return None


def _step(value: str) -> int:
    return RISK_STEPS.index(value)
