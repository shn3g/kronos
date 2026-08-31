# SPDX-License-Identifier: AGPL-3.0-or-later

from dataclasses import FrozenInstanceError

import pytest

from kronos_engine.domain.entities import (
    EventId,
    GoalId,
    IdentifierError,
    RepositoryId,
    RunId,
    TaskId,
)

ID_TYPES = (RepositoryId, GoalId, TaskId, RunId, EventId)


@pytest.mark.parametrize("cls", ID_TYPES)
def test_rejects_empty_identifier(cls: type[object]) -> None:
    with pytest.raises(IdentifierError, match="empty"):
        cls("")  # type: ignore[misc]


@pytest.mark.parametrize("cls", ID_TYPES)
@pytest.mark.parametrize("raw", [" ", "\t", "\n", "  abc", "abc  ", " a "])
def test_rejects_whitespace_in_identifier(cls: type[object], raw: str) -> None:
    with pytest.raises(IdentifierError, match="whitespace"):
        cls(raw)  # type: ignore[misc]


@pytest.mark.parametrize("cls", ID_TYPES)
def test_identifier_is_immutable_typed_value(cls: type[object]) -> None:
    ident = cls("stable-1")  # type: ignore[misc]
    assert ident.value == "stable-1"
    with pytest.raises(FrozenInstanceError):
        ident.value = "mutated"  # type: ignore[misc]


def test_distinct_identifier_types_are_not_interchangeable() -> None:
    repo = RepositoryId("same")
    goal = GoalId("same")
    assert repo.value == goal.value
    assert repo != goal
    assert type(repo) is not type(goal)
