# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pause with actionable evidence after breaker, uncertainty, or attempt limits."""

from __future__ import annotations

from dataclasses import replace

from kronos_engine.application.recorder import Recorder
from kronos_engine.domain.entities import TaskId
from kronos_engine.domain.goals import GoalState
from kronos_engine.domain.tasks import TaskRecord, TaskState, transition_task
from kronos_engine.state.goals import SqliteGoalStore


class RecoveryService:
    def __init__(self, store: SqliteGoalStore, recorder: Recorder) -> None:
        self._store = store
        self._recorder = recorder

    def pause_task(self, task_id: TaskId, *, reason: str, evidence: str) -> TaskRecord:
        task = self._store.get_task(task_id)
        if task.state in {TaskState.STOPPED, TaskState.MERGED}:
            return task
        if task.state is TaskState.PAUSED:
            updated = replace(task, stop_reason=reason)
            self._store.save_task(updated)
            return updated
        updated = replace(
            task,
            state=transition_task(task.state, TaskState.PAUSED),
            stop_reason=reason,
        )
        self._store.save_task(updated)
        self._recorder.emit(
            "task.transitioned",
            {
                "task_id": task.id.value,
                "from": task.state.value,
                "to": TaskState.PAUSED.value,
                "reason": reason,
                "evidence": evidence,
            },
        )
        self._pause_goal(task, reason)
        return updated

    def stop_task(self, task_id: TaskId, *, reason: str, evidence: str) -> TaskRecord:
        task = self._store.get_task(task_id)
        if task.state is TaskState.STOPPED:
            return replace(task, stop_reason=reason)
        if task.state is TaskState.MERGED:
            return task
        updated = replace(
            task,
            state=transition_task(task.state, TaskState.STOPPED),
            stop_reason=reason,
        )
        self._store.save_task(updated)
        self._recorder.emit(
            "task.transitioned",
            {
                "task_id": task.id.value,
                "from": task.state.value,
                "to": TaskState.STOPPED.value,
                "reason": reason,
                "evidence": evidence,
            },
        )
        goal = self._store.get_goal(task.goal_id)
        if goal.state not in {GoalState.STOPPED, GoalState.COMPLETED}:
            next_state = transition_goal_safe(goal.state, GoalState.STOPPED)
            self._store.save_goal(replace(goal, state=next_state, stop_reason=reason))
            self._recorder.emit(
                "goal.transitioned",
                {
                    "goal_id": goal.id.value,
                    "from": goal.state.value,
                    "to": next_state.value,
                    "reason": reason,
                },
            )
        return updated

    def pause_or_stop(self, task_id: TaskId, reason: str, evidence: str) -> TaskRecord:
        lowered = reason.lower()
        if "no-test" in lowered or "reproduction" in lowered:
            return self.stop_task(task_id, reason=reason, evidence=evidence)
        return self.pause_task(task_id, reason=reason, evidence=evidence)

    def _pause_goal(self, task: TaskRecord, reason: str) -> None:
        goal = self._store.get_goal(task.goal_id)
        if goal.state not in {GoalState.ACTIVE, GoalState.PLANNED}:
            return
        target = GoalState.PAUSED
        self._store.save_goal(replace(goal, state=target, stop_reason=reason))
        self._recorder.emit(
            "goal.transitioned",
            {
                "goal_id": goal.id.value,
                "from": goal.state.value,
                "to": target.value,
                "reason": reason,
            },
        )


def transition_goal_safe(current: GoalState, target: GoalState) -> GoalState:
    from kronos_engine.domain.goals import InvalidTransition, transition_goal

    try:
        return transition_goal(current, target)
    except InvalidTransition:
        return current
