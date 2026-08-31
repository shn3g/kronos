# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory secret store for tests. Production uses OS credential storage."""

from __future__ import annotations


class InMemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def put(self, name: str, value: str) -> None:
        self.values[name] = value

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def delete(self, name: str) -> None:
        self.values.pop(name, None)
