# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transactional SQLite outbox."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from kronos_engine.domain.events import OutboxRow
from kronos_engine.domain.results import AlreadyDispatchedError


class SqliteOutbox:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def enqueue(self, event_seq: int, payload: Mapping[str, object]) -> OutboxRow:
        created_at = datetime.now(tz=UTC).isoformat()
        encoded = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True)
        cursor = self._conn.execute(
            "INSERT INTO outbox(event_seq, payload, created_at) VALUES (?, ?, ?)",
            (event_seq, encoded, created_at),
        )
        outbox_id = cursor.lastrowid
        if outbox_id is None:
            raise RuntimeError("outbox insert did not assign an id")
        return OutboxRow(
            id=outbox_id,
            event_seq=event_seq,
            payload=dict(payload),
            dispatched_at=None,
        )

    def undispatched(self) -> Sequence[OutboxRow]:
        rows = self._conn.execute(
            "SELECT id, event_seq, payload, dispatched_at FROM outbox "
            "WHERE dispatched_at IS NULL ORDER BY id ASC"
        ).fetchall()
        return tuple(
            OutboxRow(
                id=row["id"],
                event_seq=row["event_seq"],
                payload=json.loads(row["payload"]),
                dispatched_at=row["dispatched_at"],
            )
            for row in rows
        )

    def mark_dispatched(self, outbox_id: int) -> None:
        dispatched_at = datetime.now(tz=UTC).isoformat()
        cursor = self._conn.execute(
            "UPDATE outbox SET dispatched_at = ? WHERE id = ? AND dispatched_at IS NULL",
            (dispatched_at, outbox_id),
        )
        if cursor.rowcount != 1:
            raise AlreadyDispatchedError(f"outbox row {outbox_id} already dispatched")
        self._conn.commit()
