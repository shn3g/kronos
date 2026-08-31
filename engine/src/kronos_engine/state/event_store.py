# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only SQLite event store."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from kronos_engine.domain.entities import EventId
from kronos_engine.domain.events import StoredEvent


class SqliteEventStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(
        self, event_id: EventId, event_type: str, payload: Mapping[str, object]
    ) -> StoredEvent:
        recorded_at = datetime.now(tz=UTC).isoformat()
        encoded = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True)
        cursor = self._conn.execute(
            "INSERT INTO events(event_id, type, payload, recorded_at) VALUES (?, ?, ?, ?)",
            (event_id.value, event_type, encoded, recorded_at),
        )
        seq = cursor.lastrowid
        if seq is None:
            raise RuntimeError("event append did not assign a sequence")
        return StoredEvent(
            id=event_id,
            type=event_type,
            payload=dict(payload),
            seq=seq,
            recorded_at=recorded_at,
        )

    def list_after(self, seq: int) -> Sequence[StoredEvent]:
        rows = self._conn.execute(
            "SELECT seq, event_id, type, payload, recorded_at FROM events "
            "WHERE seq > ? ORDER BY seq ASC",
            (seq,),
        ).fetchall()
        return tuple(
            StoredEvent(
                id=EventId(row["event_id"]),
                type=row["type"],
                payload=json.loads(row["payload"]),
                seq=row["seq"],
                recorded_at=row["recorded_at"],
            )
            for row in rows
        )

    def head_seq(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) AS head FROM events").fetchone()
        if row is None:
            return 0
        return int(row["head"])
