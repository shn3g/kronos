# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read events through the event-store port."""

from __future__ import annotations

from collections.abc import Sequence

from kronos_engine.domain.events import StoredEvent
from kronos_engine.ports.event_store import EventStore


class EventQuery:
    def __init__(self, events: EventStore) -> None:
        self._events = events

    def list_after(self, after: int) -> tuple[Sequence[StoredEvent], int]:
        return self._events.list_after(after), self._events.head_seq()
