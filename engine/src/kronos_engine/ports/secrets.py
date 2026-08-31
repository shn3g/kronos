# SPDX-License-Identifier: AGPL-3.0-or-later
"""Short-lived secrets. Values never belong in provider configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ScopedSecret:
    value: str
    ttl_seconds: int

    def __repr__(self) -> str:
        return f"ScopedSecret(ttl_seconds={self.ttl_seconds}, value=redacted)"

    def __str__(self) -> str:
        return "ScopedSecret(redacted)"


class SecretStore(Protocol):
    def put(self, name: str, value: str) -> None: ...

    def get(self, name: str) -> str | None: ...

    def delete(self, name: str) -> None: ...
