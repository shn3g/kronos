# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only catalog queries over SQLite."""

from __future__ import annotations

import sqlite3


class Catalog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_repositories(self) -> list[dict[str, str]]:
        rows = self._conn.execute("SELECT id FROM repositories ORDER BY id").fetchall()
        return [{"id": row["id"]} for row in rows]

    def list_goals(self) -> list[dict[str, str]]:
        rows = self._conn.execute(
            "SELECT id, repository_id FROM goals ORDER BY id"
        ).fetchall()
        return [{"id": row["id"], "repository_id": row["repository_id"]} for row in rows]
