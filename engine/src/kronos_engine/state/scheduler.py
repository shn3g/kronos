# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic schedules and GitHub-issue intake. Spawn requires a claimed task."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from kronos_engine.application.goals import GoalService
from kronos_engine.domain.entities import RepositoryId, TaskId
from kronos_engine.domain.goals import GoalRecord, GoalSource, GoalSpec, GoalState
from kronos_engine.domain.results import StaleFenceError
from kronos_engine.domain.tasks import TaskState
from kronos_engine.domain.workflow import (
    ScheduledSpawnForbidden,
    forbid_unbound_spawn,
    lease_resource_key,
)
from kronos_engine.ports.leases import LeaseStore
from kronos_engine.state.goals import SqliteGoalStore


class GoalScheduler:
    def __init__(
        self,
        store: SqliteGoalStore,
        goals: GoalService,
        leases: LeaseStore | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._goals = goals
        self._leases = leases
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def spawn(self, task_id: TaskId | str | None) -> TaskId:
        raw = task_id.value if isinstance(task_id, TaskId) else task_id
        bound = forbid_unbound_spawn(raw)
        ident = TaskId(bound)
        task = self._store.get_task(ident)
        if task.state is not TaskState.CLAIMED:
            raise ScheduledSpawnForbidden("scheduled spawn without a claimed task id is forbidden")
        if task.fence_token is None or self._leases is None:
            raise ScheduledSpawnForbidden("scheduled spawn without a claimed task id is forbidden")
        key = lease_resource_key(task.repository_id.value, task.scope_paths, task.id.value)
        try:
            self._leases.assert_fence(key, task.fence_token, now=self._clock())
        except StaleFenceError as error:
            raise ScheduledSpawnForbidden(str(error)) from error
        return ident

    def ingest_github_issue(
        self,
        *,
        repository_id: RepositoryId,
        title: str,
        body: str,
        non_goals: str,
        risk_ceiling: str,
        max_attempts: int,
    ) -> GoalRecord:
        criteria = body.strip() or title
        return self._goals.create(
            GoalSpec(
                repository_id=repository_id,
                title=title,
                success_criteria=criteria,
                non_goals=non_goals,
                risk_ceiling=risk_ceiling,
                source=GoalSource.GITHUB_ISSUE,
                max_attempts=max_attempts,
            )
        )

    def ingest_schedule(
        self,
        *,
        repository_id: RepositoryId,
        title: str,
        success_criteria: str,
        non_goals: str,
        schedule: str,
        max_attempts: int,
        risk_ceiling: str = "low",
    ) -> GoalRecord:
        return self._goals.create(
            GoalSpec(
                repository_id=repository_id,
                title=title,
                success_criteria=success_criteria,
                non_goals=non_goals,
                risk_ceiling=risk_ceiling,
                source=GoalSource.SCHEDULE,
                schedule=schedule,
                max_attempts=max_attempts,
            )
        )

    def tick_due(self, now: datetime) -> Sequence[GoalRecord]:
        due: list[GoalRecord] = []
        for goal in self._store.list_goals():
            if (
                goal.source is GoalSource.SCHEDULE
                and goal.state is GoalState.DRAFT
                and goal.schedule
                and goal.schedule <= now.isoformat()
            ):
                due.append(goal)
        return tuple(due)
