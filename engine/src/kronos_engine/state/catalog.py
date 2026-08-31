# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite catalog adapter."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from kronos_engine.domain.entities import Goal, GoalId, Repository, RepositoryId


class SqliteCatalog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_repositories(self) -> Sequence[Repository]:
        rows = self._conn.execute("SELECT id FROM repositories ORDER BY id").fetchall()
        return tuple(Repository(id=RepositoryId(row["id"])) for row in rows)

    def list_goals(self) -> Sequence[Goal]:
        rows = self._conn.execute(
            "SELECT id, repository_id FROM goals ORDER BY id"
        ).fetchall()
        return tuple(
            Goal(id=GoalId(row["id"]), repository_id=RepositoryId(row["repository_id"]))
            for row in rows
        )
