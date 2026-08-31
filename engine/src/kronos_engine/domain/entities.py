# SPDX-License-Identifier: AGPL-3.0-or-later
"""Immutable typed identifiers and entities. No I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kronos_engine.domain.policy import RepositoryPolicy


class IdentifierError(ValueError):
    """Raised when an identifier is empty or contains whitespace."""


def _parse_identifier(raw: object) -> str:
    if not isinstance(raw, str):
        raise IdentifierError("identifier must be a string")
    if raw == "":
        raise IdentifierError("identifier must not be empty")
    if any(ch.isspace() for ch in raw):
        raise IdentifierError("identifier must not contain whitespace")
    return raw


@dataclass(frozen=True, slots=True)
class RepositoryId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _parse_identifier(self.value))


@dataclass(frozen=True, slots=True)
class GoalId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _parse_identifier(self.value))


@dataclass(frozen=True, slots=True)
class TaskId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _parse_identifier(self.value))


@dataclass(frozen=True, slots=True)
class RunId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _parse_identifier(self.value))


@dataclass(frozen=True, slots=True)
class EventId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _parse_identifier(self.value))


class RepositoryStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class Repository:
    id: RepositoryId


@dataclass(frozen=True, slots=True)
class EnrolledRepository:
    id: RepositoryId
    realpath: str
    origin: str | None
    display_name: str
    status: RepositoryStatus
    policy: RepositoryPolicy
    enrolled_at: str


@dataclass(frozen=True, slots=True)
class Goal:
    id: GoalId
    repository_id: RepositoryId


@dataclass(frozen=True, slots=True)
class Lease:
    resource_key: str
    holder_id: str
    fence_token: int
    expires_at: datetime
