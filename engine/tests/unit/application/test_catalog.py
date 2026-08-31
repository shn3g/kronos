# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import kronos_engine.application.catalog as catalog_mod
from kronos_engine.application.catalog import CatalogService
from kronos_engine.domain.entities import Goal, GoalId, Repository, RepositoryId


class _FakeCatalog:
    def list_repositories(self) -> Sequence[Repository]:
        return (Repository(id=RepositoryId("repo-1")),)

    def list_goals(self) -> Sequence[Goal]:
        return (Goal(id=GoalId("goal-1"), repository_id=RepositoryId("repo-1")),)


def test_catalog_service_reads_through_a_port() -> None:
    service = CatalogService(_FakeCatalog())
    assert [repo.id.value for repo in service.list_repositories()] == ["repo-1"]
    goals = list(service.list_goals())
    assert goals[0].id.value == "goal-1"
    assert goals[0].repository_id.value == "repo-1"


def test_application_catalog_does_not_execute_sql() -> None:
    assert catalog_mod.__file__ is not None
    source = Path(catalog_mod.__file__).read_text(encoding="utf-8")
    assert "sqlite3" not in source
    assert "SELECT" not in source
