# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite repository registry adapter."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from kronos_engine.domain.entities import EnrolledRepository, RepositoryId, RepositoryStatus
from kronos_engine.domain.policy import parse_policy


class SqliteRepositoryRegistry:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, repo_id: RepositoryId) -> EnrolledRepository | None:
        row = self._conn.execute(
            "SELECT id, realpath, origin, display_name, status, policy_json, enrolled_at "
            "FROM repositories WHERE id = ?",
            (repo_id.value,),
        ).fetchone()
        return None if row is None else _from_row(row)

    def get_by_realpath(self, realpath: str) -> EnrolledRepository | None:
        row = self._conn.execute(
            "SELECT id, realpath, origin, display_name, status, policy_json, enrolled_at "
            "FROM repositories WHERE realpath = ?",
            (realpath,),
        ).fetchone()
        return None if row is None else _from_row(row)

    def list(self) -> Sequence[EnrolledRepository]:
        rows = self._conn.execute(
            "SELECT id, realpath, origin, display_name, status, policy_json, enrolled_at "
            "FROM repositories ORDER BY display_name, id"
        ).fetchall()
        return tuple(_from_row(row) for row in rows)

    def save(self, repo: EnrolledRepository) -> None:
        from kronos_engine.domain.policy import policy_to_dict

        payload = json.dumps(policy_to_dict(repo.policy))
        self._conn.execute(
            """
            INSERT INTO repositories(
                id, realpath, origin, display_name, status, policy_json, enrolled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                realpath = excluded.realpath,
                origin = excluded.origin,
                display_name = excluded.display_name,
                status = excluded.status,
                policy_json = excluded.policy_json
            """,
            (
                repo.id.value,
                repo.realpath,
                repo.origin,
                repo.display_name,
                repo.status.value,
                payload,
                repo.enrolled_at,
            ),
        )
        self._conn.commit()

    def delete(self, repo_id: RepositoryId) -> None:
        self._conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id.value,))
        self._conn.commit()


def _from_row(row: sqlite3.Row) -> EnrolledRepository:
    return EnrolledRepository(
        id=RepositoryId(row["id"]),
        realpath=row["realpath"],
        origin=row["origin"],
        display_name=row["display_name"],
        status=RepositoryStatus(row["status"]),
        policy=parse_policy(json.loads(row["policy_json"])),
        enrolled_at=row["enrolled_at"],
    )
