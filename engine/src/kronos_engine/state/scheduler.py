# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic schedules and GitHub-issue intake. Spawn requires a claimed task id."""

from __future__ import annotations

from kronos_engine.application.goals import GoalService
from kronos_engine.domain.entities import RepositoryId, TaskId
from kronos_engine.domain.goals import GoalSource, GoalSpec
from kronos_engine.domain.workflow import forbid_unbound_spawn
from kronos_engine.state.goals import SqliteGoalStore


class GoalScheduler:
    def __init__(self, store: SqliteGoalStore, goals: GoalService) -> None:
        self._store = store
        self._goals = goals

    def spawn(self, task_id: TaskId | str | None) -> TaskId:
        raw = task_id.value if isinstance(task_id, TaskId) else task_id
        bound = forbid_unbound_spawn(raw)
        return TaskId(bound)

    def ingest_github_issue(
        self,
        *,
        repository_id: RepositoryId,
        title: str,
        body: str,
    ) -> object:
        criteria = body.strip() or title
        return self._goals.create(
            GoalSpec(
                repository_id=repository_id,
                title=title,
                success_criteria=criteria,
                non_goals="not specified in the GitHub issue",
                risk_ceiling="medium",
                source=GoalSource.GITHUB_ISSUE,
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
    ) -> object:
        return self._goals.create(
            GoalSpec(
                repository_id=repository_id,
                title=title,
                success_criteria=success_criteria,
                non_goals=non_goals,
                risk_ceiling="low",
                source=GoalSource.SCHEDULE,
                schedule=schedule,
            )
        )
