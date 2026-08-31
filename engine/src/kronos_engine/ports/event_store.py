# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event store port."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from kronos_engine.domain.entities import EventId
from kronos_engine.domain.events import StoredEvent


class EventStore(Protocol):
    def append(
        self, event_id: EventId, event_type: str, payload: Mapping[str, object]
    ) -> StoredEvent: ...

    def list_after(self, seq: int) -> Sequence[StoredEvent]: ...

    def head_seq(self) -> int: ...
