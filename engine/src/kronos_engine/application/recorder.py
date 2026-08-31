# SPDX-License-Identifier: AGPL-3.0-or-later
"""Record a domain event and its outbox row in one SQLite transaction."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from kronos_engine.domain.entities import EventId
from kronos_engine.domain.events import OutboxRow, StoredEvent
from kronos_engine.ports.event_store import EventStore
from kronos_engine.ports.outbox import Outbox


class Recorder:
    def __init__(self, conn: sqlite3.Connection, events: EventStore, outbox: Outbox) -> None:
        self._conn = conn
        self._events = events
        self._outbox = outbox

    def record(
        self,
        event_id: EventId,
        event_type: str,
        payload: Mapping[str, object],
        outbox_payload: Mapping[str, object],
    ) -> tuple[StoredEvent, OutboxRow]:
        try:
            stored = self._events.append(event_id, event_type, payload)
            row = self._outbox.enqueue(stored.seq, outbox_payload)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return stored, row
