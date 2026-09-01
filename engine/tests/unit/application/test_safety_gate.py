# SPDX-License-Identifier: AGPL-3.0-or-later
"""PR write modes stay closed until ruleset, workflow, CODEOWNERS, and reviewer verify."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.application.safety import SafetyElevationRefused
from kronos_engine.config.paths import resolve_paths
from kronos_engine.ports.forge import GithubAppRecord
from kronos_engine.state.database import Database
from kronos_engine.state.github_apps import MemoryGithubAppStore
from kronos_engine.state.repositories import SqliteRepositoryRegistry


class _FakeForge:
    def __init__(self, *, strict: bool) -> None:
        self._strict = strict

    def ruleset_strict(self) -> bool:
        return self._strict


def _service(
    tmp_path: Path,
    *,
    forge: _FakeForge,
    reviewer: GithubAppRecord | None,
) -> RepositoryService:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    for directory in (paths.data, paths.config, paths.cache, paths.logs, paths.worktrees):
        directory.mkdir(parents=True, exist_ok=True)
    conn = Database(paths.database).connect()
    apps = MemoryGithubAppStore()
    if reviewer is not None:
        apps.save(reviewer)
    return RepositoryService(
        registry=SqliteRepositoryRegistry(conn),
        paths=paths,
        inspector=FilesystemGitInspector(),
        detector=ManifestStackDetector(),
        runtime=CacheRuntimeLayout(),
        apps=apps,
        forge_for=lambda _record: forge,
    )


def _unverified_reviewer() -> GithubAppRecord:
    return GithubAppRecord(
        role="reviewer",
        app_id=9001,
        slug="kronos-reviewer",
        installation_id=2002,
        verified_at=None,
    )


def test_set_operation_mode_refuses_write_draft_prs_without_protection(tmp_path: Path) -> None:
    root = init_git_repo(
        tmp_path / "app",
        origin="https://github.com/acme/app.git",
        files={"README.md": "app\n"},
    )
    service = _service(
        tmp_path,
        forge=_FakeForge(strict=False),
        reviewer=_unverified_reviewer(),
    )
    enrolled = service.enrol(str(root))
    with pytest.raises(SafetyElevationRefused, match="safety"):
        service.set_operation_mode(enrolled.id, "write_draft_prs")
    assert service.get(enrolled.id).policy.autonomy.mode == "observe"


def test_write_issues_does_not_require_pr_safety_gate(tmp_path: Path) -> None:
    root = init_git_repo(
        tmp_path / "app",
        origin="https://github.com/acme/app.git",
        files={"README.md": "app\n"},
    )
    service = _service(
        tmp_path,
        forge=_FakeForge(strict=False),
        reviewer=_unverified_reviewer(),
    )
    enrolled = service.enrol(str(root))
    updated = service.set_operation_mode(enrolled.id, "write_issues", freeze=False)
    assert updated.policy.autonomy.mode == "write_issues"
    assert updated.policy.autonomy.freeze is False
