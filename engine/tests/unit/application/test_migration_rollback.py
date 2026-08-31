# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rollback freezes Kronos autonomy and leaves operator wrappers as fallback."""

from __future__ import annotations

from pathlib import Path

from tests.support.git_fixtures import init_git_repo

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.application.migration import rollback_to_wrappers
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.paths import resolve_paths
from kronos_engine.indexing.service import IndexingService
from kronos_engine.state.database import Database
from kronos_engine.state.repositories import SqliteRepositoryRegistry


def test_rollback_freezes_kronos_and_does_not_reenable_wrappers(tmp_path: Path) -> None:
    paths = resolve_paths(
        {
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    db = Database(paths.database)
    repos = RepositoryService(
        SqliteRepositoryRegistry(db.connect()),
        paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
        indexer=IndexingService(paths),
    )
    root = init_git_repo(
        tmp_path / "sample-app",
        origin="https://github.com/acme/sample-app.git",
        files={"README.md": "sample\n"},
    )
    enrolled = repos.enrol(
        str(root),
        {
            "autonomy": {
                "freeze": False,
                "invent_issues": False,
                "refill_enabled": False,
                "mode": "shadow",
            },
            "branches": {"integration": "main-openclaw", "protected": "main"},
        },
    )
    plan = rollback_to_wrappers(repos, enrolled.id)
    frozen = repos.get(enrolled.id)
    assert plan.frozen is True
    assert plan.wrappers_reenabled is False
    assert plan.write_crons_enabled is False
    assert "wrapper" in plan.fallback.lower()
    assert frozen.policy.autonomy.freeze is True
    assert frozen.policy.autonomy.invent_issues is False
    assert frozen.policy.autonomy.mode == "shadow"
    assert frozen.status.value == "paused"
