# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lease port with fencing tokens."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from kronos_engine.domain.entities import Lease


class LeaseStore(Protocol):
    def acquire(
        self,
        resource_key: str,
        holder_id: str,
        ttl: timedelta,
        *,
        now: datetime,
    ) -> Lease: ...

    def assert_fence(
        self, resource_key: str, fence_token: int, *, now: datetime
    ) -> Lease: ...
