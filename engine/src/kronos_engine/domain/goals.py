# SPDX-License-Identifier: AGPL-3.0-or-later
"""Goal states, required fields, and invalid-transition errors. No I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kronos_engine.domain.entities import GoalId, RepositoryId
from kronos_engine.domain.policy import RISK_STEPS


class InvalidTransition(ValueError):
    """Raised when a goal or task state change is not allowed."""


class GoalValidationError(ValueError):
    """Raised when a goal is missing required fields."""


class GoalState(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"


class GoalSource(StrEnum):
    DESKTOP = "desktop"
    API = "api"
    CLI = "cli"
    GITHUB_ISSUE = "github_issue"
    SCHEDULE = "schedule"


GOAL_TRANSITIONS: dict[GoalState, frozenset[GoalState]] = {
    GoalState.DRAFT: frozenset({GoalState.PLANNED, GoalState.STOPPED}),
    GoalState.PLANNED: frozenset({GoalState.ACTIVE, GoalState.PAUSED, GoalState.STOPPED}),
    GoalState.ACTIVE: frozenset(
        {GoalState.PAUSED, GoalState.COMPLETED, GoalState.STOPPED, GoalState.PLANNED}
    ),
    GoalState.PAUSED: frozenset({GoalState.ACTIVE, GoalState.STOPPED, GoalState.PLANNED}),
    GoalState.COMPLETED: frozenset(),
    GoalState.STOPPED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class GoalSpec:
    repository_id: RepositoryId
    title: str
    success_criteria: str
    non_goals: str
    risk_ceiling: str
    source: GoalSource
    max_attempts: int
    schedule: str | None = None

    def __post_init__(self) -> None:
        require_goal_fields(self)


@dataclass(frozen=True, slots=True)
class GoalRecord:
    id: GoalId
    repository_id: RepositoryId
    title: str
    success_criteria: str
    non_goals: str
    risk_ceiling: str
    source: GoalSource
    state: GoalState
    max_attempts: int = 3
    schedule: str | None = None
    stop_reason: str | None = None
    created_at: str = ""


def require_goal_fields(spec: GoalSpec) -> None:
    if spec.title.strip() == "":
        raise GoalValidationError("title is required")
    if spec.success_criteria.strip() == "":
        raise GoalValidationError("success criteria are required")
    if spec.non_goals.strip() == "":
        raise GoalValidationError("non-goals are required")
    if spec.risk_ceiling not in RISK_STEPS:
        raise GoalValidationError("risk ceiling is required")
    if spec.max_attempts < 1:
        raise GoalValidationError("budget is required")
    if spec.source is GoalSource.SCHEDULE and (
        spec.schedule is None or spec.schedule.strip() == ""
    ):
        raise GoalValidationError("schedule is required for scheduled goals")


def transition_goal(current: GoalState, target: GoalState) -> GoalState:
    allowed = GOAL_TRANSITIONS[current]
    if target not in allowed:
        raise InvalidTransition(f"cannot transition goal from {current} to {target}")
    return target
