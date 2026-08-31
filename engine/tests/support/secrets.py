# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory secret doubles. Production uses OS credential storage."""

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


class MemoryKeyring:
    """OS-credential-shaped backend for tests. Does not write files."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    @property
    def name(self) -> str:
        return "memory"

    def set_password(self, service: str, username: str, password: str) -> None:
        self._values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._values.pop((service, username), None)
