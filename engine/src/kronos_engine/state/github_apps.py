# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite GitHub App metadata. Private keys and tokens never belong here."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from kronos_engine.ports.forge import GithubAppRecord


class MemoryGithubAppStore:
    def __init__(self) -> None:
        self._rows: dict[str, GithubAppRecord] = {}

    def save(self, record: GithubAppRecord) -> None:
        self._rows[record.role] = record

    def get(self, role: str) -> GithubAppRecord | None:
        return self._rows.get(role)

    def list(self) -> Sequence[GithubAppRecord]:
        return tuple(self._rows[role] for role in sorted(self._rows))


class SqliteGithubAppStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, record: GithubAppRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO github_apps(role, app_id, slug, installation_id, verified_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(role) DO UPDATE SET
                app_id = excluded.app_id,
                slug = excluded.slug,
                installation_id = excluded.installation_id,
                verified_at = excluded.verified_at
            """,
            (
                record.role,
                record.app_id,
                record.slug,
                record.installation_id,
                record.verified_at,
            ),
        )
        self._conn.commit()

    def get(self, role: str) -> GithubAppRecord | None:
        row = self._conn.execute(
            "SELECT role, app_id, slug, installation_id, verified_at "
            "FROM github_apps WHERE role = ?",
            (role,),
        ).fetchone()
        if row is None:
            return None
        return GithubAppRecord(
            role=row["role"],
            app_id=int(row["app_id"]),
            slug=row["slug"],
            installation_id=row["installation_id"],
            verified_at=row["verified_at"],
        )

    def list(self) -> Sequence[GithubAppRecord]:
        rows = self._conn.execute(
            "SELECT role, app_id, slug, installation_id, verified_at "
            "FROM github_apps ORDER BY role"
        ).fetchall()
        return tuple(
            GithubAppRecord(
                role=row["role"],
                app_id=int(row["app_id"]),
                slug=row["slug"],
                installation_id=row["installation_id"],
                verified_at=row["verified_at"],
            )
            for row in rows
        )
