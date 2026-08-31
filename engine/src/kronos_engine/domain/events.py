# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain events. Pure values with no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kronos_engine.domain.entities import EventId


@dataclass(frozen=True, slots=True)
class StoredEvent:
    id: EventId
    type: str
    payload: Mapping[str, object]
    seq: int
    recorded_at: str


@dataclass(frozen=True, slots=True)
class OutboxRow:
    id: int
    event_seq: int
    payload: Mapping[str, object]
    dispatched_at: str | None
