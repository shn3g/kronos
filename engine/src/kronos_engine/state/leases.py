# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite TTL leases with fencing tokens."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from kronos_engine.domain.entities import Lease
from kronos_engine.domain.results import LockHeldError, StaleFenceError

_MAX_ATTEMPTS = 8


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
        last_error: Exception | None = None
        for _ in range(_MAX_ATTEMPTS):
            try:
                return self._acquire_once(resource_key, holder_id, expires_at, now)
            except _Retry as error:
                last_error = error
                continue
        raise LockHeldError(f"live lease held for {resource_key}") from last_error

    def _acquire_once(
        self,
        resource_key: str,
        holder_id: str,
        expires_at: datetime,
        now: datetime,
    ) -> Lease:
        now_iso = now.isoformat()
        expires_iso = expires_at.isoformat()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                "SELECT holder_id, fence_token, expires_at FROM leases WHERE resource_key = ?",
                (resource_key,),
            ).fetchone()
            if row is None:
                try:
                    self._conn.execute(
                        "INSERT INTO leases(resource_key, holder_id, fence_token, expires_at) "
                        "VALUES (?, ?, ?, ?)",
                        (resource_key, holder_id, 1, expires_iso),
                    )
                except sqlite3.IntegrityError as error:
                    self._conn.rollback()
                    raise _Retry from error
                self._conn.commit()
                return Lease(resource_key, holder_id, 1, expires_at)

            current = _lease_from_row(resource_key, row)
            if current.expires_at <= now:
                cursor = self._conn.execute(
                    "UPDATE leases SET holder_id = ?, fence_token = ?, expires_at = ? "
                    "WHERE resource_key = ? AND fence_token = ? AND expires_at <= ?",
                    (
                        holder_id,
                        current.fence_token + 1,
                        expires_iso,
                        resource_key,
                        current.fence_token,
                        now_iso,
                    ),
                )
                if cursor.rowcount != 1:
                    self._conn.rollback()
                    raise _Retry
                self._conn.commit()
                return Lease(resource_key, holder_id, current.fence_token + 1, expires_at)

            if current.holder_id != holder_id:
                self._conn.rollback()
                raise LockHeldError(f"live lease held for {resource_key}")

            cursor = self._conn.execute(
                "UPDATE leases SET expires_at = ? "
                "WHERE resource_key = ? AND fence_token = ? AND holder_id = ? AND expires_at > ?",
                (expires_iso, resource_key, current.fence_token, holder_id, now_iso),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                raise _Retry
            self._conn.commit()
            return Lease(resource_key, holder_id, current.fence_token, expires_at)
        except _Retry:
            raise
        except LockHeldError:
            raise
        except sqlite3.Error:
            self._conn.rollback()
            raise

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


class _Retry(Exception):
    """Internal signal to retry a fenced write after a lost race."""


def _lease_from_row(resource_key: str, row: sqlite3.Row) -> Lease:
    return Lease(
        resource_key=resource_key,
        holder_id=row["holder_id"],
        fence_token=row["fence_token"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )
