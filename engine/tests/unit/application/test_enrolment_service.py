# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo

import kronos_engine.application.repositories as repositories_mod
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.paths import resolve_paths
from kronos_engine.domain.entities import RepositoryId
from kronos_engine.domain.policy import PolicyError
from kronos_engine.state.database import Database
from kronos_engine.state.repositories import SqliteRepositoryRegistry

PYPROJECT = "[project]\nname='alpha'\n[tool.pytest.ini_options]\ntestpaths=['tests']\n"


def _service(tmp_path: Path) -> RepositoryService:
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
    database = Database(paths.database)
    conn = database.connect()
    return RepositoryService(registry=SqliteRepositoryRegistry(conn), paths=paths)


def test_enrol_inspect_and_lifecycle_keep_runtime_out_of_the_tree(tmp_path: Path) -> None:
    service = _service(tmp_path)
    python_root = init_git_repo(
        tmp_path / "alpha",
        origin="https://github.com/acme/alpha.git",
        files={"pyproject.toml": PYPROJECT, "README.md": "alpha\n"},
    )
    node_root = init_git_repo(
        tmp_path / "beta",
        origin="https://github.com/acme/beta.git",
        files={
            "package.json": '{"name":"beta","scripts":{"test":"vitest"}}',
            "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
            "README.md": "beta\n",
        },
    )

    inspection = service.inspect(str(python_root))
    assert inspection.git_root == str(python_root.resolve())
    assert inspection.wrote_files is False
    assert not (python_root / ".kronos").exists()

    alpha = service.enrol(str(python_root))
    beta = service.enrol(str(node_root), policy_overrides={"autonomy": {"freeze": False}})
    assert alpha.id != beta.id
    assert alpha.status.value == "active"
    assert beta.policy.autonomy.freeze is False
    assert alpha.policy.autonomy.freeze is True
    assert service.get(alpha.id).policy.autonomy.freeze is True
    assert service.get(beta.id).policy.autonomy.freeze is False

    listed = {item.id.value: item for item in service.list()}
    assert set(listed) == {alpha.id.value, beta.id.value}

    with pytest.raises(LookupError):
        service.get(RepositoryId("repo_does-not-exist"))
    leaked = service.get(beta.id)
    assert leaked.policy.autonomy.freeze is False
    assert leaked.id != alpha.id
    assert service.get(alpha.id).realpath != leaked.realpath

    paused = service.pause(alpha.id)
    assert paused.status.value == "paused"
    disabled = service.disable(beta.id)
    assert disabled.status.value == "disabled"
    service.remove(alpha.id)
    assert python_root.exists()
    assert (python_root / ".git").exists()
    assert all(item.id != alpha.id for item in service.list())
    restored = service.reenrol(path=str(python_root))
    assert restored.id == alpha.id
    assert restored.status.value == "active"

    for root in (python_root, node_root):
        names = {path.name for path in root.iterdir()}
        assert ".kronos" not in names
        assert "kronos.sqlite3" not in names
        assert ".worktrees" not in names
        runtime_marker = list(root.rglob("kronos.sqlite3")) + list(root.rglob("TICKET.md"))
        assert runtime_marker == []

    runtime = service.runtime_paths(beta.id)
    assert python_root.resolve() not in Path(runtime.state_dir).parents
    assert python_root.resolve() != Path(runtime.state_dir)
    assert "worktrees" in runtime.worktrees.replace("\\", "/")
    assert beta.id.value in runtime.worktrees

    again = service.enrol(str(node_root))
    assert again.id == beta.id


def test_models_cannot_patch_enrolled_policy_to_raise_budgets(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = init_git_repo(tmp_path / "gamma", origin="https://github.com/acme/gamma.git")
    enrolled = service.enrol(str(root))
    with pytest.raises(PolicyError, match="budget"):
        service.apply_model_policy(
            enrolled.id,
            {
                "schema_version": 1,
                "branches": {
                    "integration": enrolled.policy.branches.integration,
                    "protected": enrolled.policy.branches.protected,
                },
                "commands": {
                    "setup": list(enrolled.policy.commands.setup),
                    "test": list(enrolled.policy.commands.test),
                    "lint": list(enrolled.policy.commands.lint),
                    "build": list(enrolled.policy.commands.build),
                },
                "autonomy": {
                    "freeze": enrolled.policy.autonomy.freeze,
                    "invent_issues": enrolled.policy.autonomy.invent_issues,
                    "refill_enabled": enrolled.policy.autonomy.refill_enabled,
                },
                "paths": {"locked_prefixes": list(enrolled.policy.paths.locked_prefixes)},
                "risk": {"floor": enrolled.policy.risk.floor},
                "budgets": {
                    "max_attempts_per_issue": 99,
                    "max_dispatches_per_day": enrolled.policy.budgets.max_dispatches_per_day,
                    "breaker_failure_limit": enrolled.policy.budgets.breaker_failure_limit,
                    "dry_run_meters": False,
                },
                "wip": {"ready": enrolled.policy.wip.ready, "running": enrolled.policy.wip.running},
                "executor": {
                    "profile": enrolled.policy.executor.profile,
                    "sandbox": enrolled.policy.executor.sandbox,
                },
                "indexing": {"enabled": enrolled.policy.indexing.enabled},
            },
        )


def test_application_repositories_do_not_execute_sql() -> None:
    assert repositories_mod.__file__ is not None
    source = Path(repositories_mod.__file__).read_text(encoding="utf-8")
    assert "sqlite3" not in source
    assert "SELECT" not in source
