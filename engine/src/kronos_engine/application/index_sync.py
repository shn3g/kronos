# SPDX-License-Identifier: AGPL-3.0-or-later
"""Background working-tree index refresh for enrolled repositories."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.paths import KronosPaths
from kronos_engine.domain.entities import RepositoryStatus
from kronos_engine.indexing.service import IndexingService
from kronos_engine.observability.logging import get_logger
from kronos_engine.state.database import Database
from kronos_engine.state.repositories import SqliteRepositoryRegistry

INDEX_SYNC_INTERVAL_SECONDS = 2.0


def sync_enrolled_indexes(database: Database, paths: KronosPaths) -> int:
    conn = database.connect()
    updated = 0
    try:
        repos = RepositoryService(
            SqliteRepositoryRegistry(conn),
            paths,
            FilesystemGitInspector(),
            ManifestStackDetector(),
            CacheRuntimeLayout(),
        )
        indexer = IndexingService(paths)
        for record in repos.list():
            if record.status != RepositoryStatus.ACTIVE:
                continue
            try:
                indexer.incremental(record.id.value, Path(record.realpath), record.policy)
                updated += 1
            except Exception:
                get_logger("kronos.index").exception(
                    "index sync failed for %s", record.id.value
                )
    finally:
        conn.close()
    return updated
