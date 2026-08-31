# SPDX-License-Identifier: AGPL-3.0-or-later
"""Record a domain event and its outbox row in one SQLite transaction."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Mapping

from kronos_engine.domain.entities import EventId
from kronos_engine.domain.events import OutboxRow, StoredEvent
from kronos_engine.observability.redaction import redact_mapping
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
        cleaned = redact_mapping(payload)
        cleaned_outbox = redact_mapping(outbox_payload)
        try:
            stored = self._events.append(event_id, event_type, cleaned)
            row = self._outbox.enqueue(stored.seq, cleaned_outbox)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return stored, row

    def emit(self, event_type: str, payload: Mapping[str, object]) -> tuple[StoredEvent, OutboxRow]:
        event_id = EventId(f"evt_{uuid.uuid4().hex[:16]}")
        return self.record(event_id, event_type, payload, payload)
