# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite TTL leases with fencing tokens."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from kronos_engine.domain.entities import Lease
from kronos_engine.domain.results import LockHeldError, StaleFenceError


class SqliteLeases:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def acquire(
        self,
        resource_key: str,
        holder_id: str,
        ttl: timedelta,
        *,
        now: datetime,
    ) -> Lease:
        expires_at = now + ttl
        row = self._conn.execute(
            "SELECT holder_id, fence_token, expires_at FROM leases WHERE resource_key = ?",
            (resource_key,),
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO leases(resource_key, holder_id, fence_token, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (resource_key, holder_id, 1, expires_at.isoformat()),
            )
            self._conn.commit()
            return Lease(resource_key, holder_id, 1, expires_at)

        current = _lease_from_row(resource_key, row)
        if current.expires_at <= now:
            token = current.fence_token + 1
            self._conn.execute(
                "UPDATE leases SET holder_id = ?, fence_token = ?, expires_at = ? "
                "WHERE resource_key = ?",
                (holder_id, token, expires_at.isoformat(), resource_key),
            )
            self._conn.commit()
            return Lease(resource_key, holder_id, token, expires_at)

        if current.holder_id != holder_id:
            raise LockHeldError(f"live lease held for {resource_key}")

        self._conn.execute(
            "UPDATE leases SET expires_at = ? WHERE resource_key = ? AND fence_token = ?",
            (expires_at.isoformat(), resource_key, current.fence_token),
        )
        self._conn.commit()
        return Lease(resource_key, holder_id, current.fence_token, expires_at)

    def assert_fence(self, resource_key: str, fence_token: int, *, now: datetime) -> Lease:
        row = self._conn.execute(
            "SELECT holder_id, fence_token, expires_at FROM leases WHERE resource_key = ?",
            (resource_key,),
        ).fetchone()
        if row is None:
            raise StaleFenceError(f"no lease for {resource_key}")
        current = _lease_from_row(resource_key, row)
        if current.expires_at <= now or current.fence_token != fence_token:
            raise StaleFenceError(f"stale fence for {resource_key}")
        return current


def _lease_from_row(resource_key: str, row: sqlite3.Row) -> Lease:
    return Lease(
        resource_key=resource_key,
        holder_id=row["holder_id"],
        fence_token=row["fence_token"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )
