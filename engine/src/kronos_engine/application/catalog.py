# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only catalog queries. Depends on a catalog port, not SQL."""

from __future__ import annotations

from collections.abc import Sequence

from kronos_engine.domain.entities import Goal, Repository
from kronos_engine.ports.catalog import Catalog


class CatalogService:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def list_repositories(self) -> Sequence[Repository]:
        return self._catalog.list_repositories()

    def list_goals(self) -> Sequence[Goal]:
        return self._catalog.list_goals()
