# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create, list, and transition bounded goals. Ports only, no FastAPI."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryNotFound, RepositoryService
from kronos_engine.domain.entities import GoalId
from kronos_engine.domain.goals import GoalRecord, GoalSpec, GoalState, transition_goal
from kronos_engine.domain.tasks import RunRecord, TaskRecord
from kronos_engine.state.goals import SqliteGoalStore


class GoalService:
    def __init__(
        self,
        store: SqliteGoalStore,
        repos: RepositoryService,
        recorder: Recorder,
    ) -> None:
        self._store = store
        self._repos = repos
        self._recorder = recorder

    def create(self, spec: GoalSpec) -> GoalRecord:
        try:
            self._repos.get(spec.repository_id)
        except RepositoryNotFound as error:
            raise LookupError("repository not found") from error
        goal = GoalRecord(
            id=GoalId(f"goal_{uuid4().hex[:16]}"),
            repository_id=spec.repository_id,
            title=spec.title,
            success_criteria=spec.success_criteria,
            non_goals=spec.non_goals,
            risk_ceiling=spec.risk_ceiling,
            source=spec.source,
            state=GoalState.DRAFT,
            max_attempts=spec.max_attempts,
            schedule=spec.schedule,
            created_at=datetime.now(tz=UTC).isoformat(),
        )
        self._store.save_goal(goal)
        self._recorder.emit(
            "goal.created",
            {
                "goal_id": goal.id.value,
                "repository_id": goal.repository_id.value,
                "state": goal.state.value,
                "source": goal.source.value,
            },
        )
        return goal

    def list(self) -> Sequence[GoalRecord]:
        return self._store.list_goals()

    def get(self, goal_id: GoalId) -> GoalRecord:
        return self._store.get_goal(goal_id)

    def list_tasks(self, goal_id: GoalId) -> Sequence[TaskRecord]:
        return self._store.list_tasks(goal_id)

    def list_runs(self) -> Sequence[RunRecord]:
        return self._store.list_runs()

    def transition(
        self, goal_id: GoalId, target: GoalState, *, reason: str | None = None
    ) -> GoalRecord:
        goal = self._store.get_goal(goal_id)
        next_state = transition_goal(goal.state, target)
        updated = GoalRecord(
            id=goal.id,
            repository_id=goal.repository_id,
            title=goal.title,
            success_criteria=goal.success_criteria,
            non_goals=goal.non_goals,
            risk_ceiling=goal.risk_ceiling,
            source=goal.source,
            state=next_state,
            max_attempts=goal.max_attempts,
            schedule=goal.schedule,
            stop_reason=reason if reason is not None else goal.stop_reason,
            created_at=goal.created_at,
        )
        self._store.save_goal(updated)
        self._recorder.emit(
            "goal.transitioned",
            {
                "goal_id": updated.id.value,
                "from": goal.state.value,
                "to": updated.state.value,
                "reason": updated.stop_reason or "",
            },
        )
        return updated
