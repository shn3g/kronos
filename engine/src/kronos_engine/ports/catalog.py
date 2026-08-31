# SPDX-License-Identifier: AGPL-3.0-or-later
"""Catalog port. Application depends on this; adapters implement it."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from kronos_engine.domain.entities import Goal, Repository


class Catalog(Protocol):
    def list_repositories(self) -> Sequence[Repository]: ...

    def list_goals(self) -> Sequence[Goal]: ...
