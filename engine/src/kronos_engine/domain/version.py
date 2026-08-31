# SPDX-License-Identifier: AGPL-3.0-or-later
"""Client/engine version compatibility. Pure functions, no I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> SemVer | None:
        parts = raw.strip().split(".")
        if len(parts) != 3:
            return None
        try:
            numbers = tuple(int(part) for part in parts)
        except ValueError:
            return None
        if any(number < 0 for number in numbers):
            return None
        return cls(numbers[0], numbers[1], numbers[2])


def client_is_compatible(client_version: str, min_client_version: str, engine_version: str) -> bool:
    client = SemVer.parse(client_version)
    minimum = SemVer.parse(min_client_version)
    engine = SemVer.parse(engine_version)
    if client is None or minimum is None or engine is None:
        return False
    if client.major != engine.major:
        return False
    return (client.major, client.minor, client.patch) >= (
        minimum.major,
        minimum.minor,
        minimum.patch,
    )
