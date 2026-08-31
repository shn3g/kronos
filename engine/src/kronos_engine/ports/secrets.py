# SPDX-License-Identifier: AGPL-3.0-or-later
"""Short-lived secrets. Values never belong in provider configuration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


class SecretExpiredError(RuntimeError):
    """Raised when a scoped secret is used after its TTL."""


@dataclass(frozen=True, slots=True)
class ScopedSecret:
    value: str
    ttl_seconds: int
    issued_at: float = field(default_factory=time.monotonic)

    def expired(self, now: float | None = None) -> bool:
        clock = time.monotonic() if now is None else now
        return clock >= self.issued_at + self.ttl_seconds

    def require_fresh(self, now: float | None = None) -> str:
        if self.expired(now):
            raise SecretExpiredError("scoped secret expired")
        return self.value

    def __repr__(self) -> str:
        return f"ScopedSecret(ttl_seconds={self.ttl_seconds}, value=redacted)"

    def __str__(self) -> str:
        return "ScopedSecret(redacted)"


class SecretStore(Protocol):
    def put(self, name: str, value: str) -> None: ...

    def get(self, name: str) -> str | None: ...

    def delete(self, name: str) -> None: ...
