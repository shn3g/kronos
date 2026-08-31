# SPDX-License-Identifier: AGPL-3.0-or-later
"""Outbox port."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from kronos_engine.domain.events import OutboxRow


class Outbox(Protocol):
    def enqueue(self, event_seq: int, payload: Mapping[str, object]) -> OutboxRow: ...

    def undispatched(self) -> Sequence[OutboxRow]: ...

    def mark_dispatched(self, outbox_id: int) -> None: ...
