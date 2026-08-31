# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo

import kronos_engine.application.repositories as repositories_mod
from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.application.repositories import RepositoryService, stable_repository_id
from kronos_engine.config.paths import resolve_paths
from kronos_engine.domain.entities import RepositoryId
from kronos_engine.domain.policy import Commands, PolicyError
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
    return RepositoryService(
        registry=SqliteRepositoryRegistry(conn),
        paths=paths,
        inspector=FilesystemGitInspector(),
        detector=ManifestStackDetector(),
        runtime=CacheRuntimeLayout(),
    )


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


def test_application_repositories_depend_on_ports_not_adapters() -> None:
    assert repositories_mod.__file__ is not None
    source = Path(repositories_mod.__file__).read_text(encoding="utf-8")
    assert "kronos_engine.adapters" not in source
    assert ".mkdir(" not in source


def test_repository_service_uses_injected_ports(tmp_path: Path) -> None:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    for directory in (paths.data, paths.config, paths.cache, paths.logs):
        directory.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "not-a-git-folder"
    root.mkdir()
    runtime = _FakeRuntime()
    service = RepositoryService(
        registry=SqliteRepositoryRegistry(Database(paths.database).connect()),
        paths=paths,
        inspector=_FakeInspector(root),
        detector=_FakeDetector(),
        runtime=runtime,
    )
    enrolled = service.enrol(str(root), policy_overrides={"autonomy": {"freeze": False}})
    assert enrolled.policy.autonomy.freeze is False
    assert runtime.ensured
    assert Path(runtime.ensured[0][2]) == root


def test_resume_keeps_stored_policy_after_pause(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = init_git_repo(tmp_path / "paused", origin="https://github.com/acme/paused.git")
    enrolled = service.enrol(str(root), policy_overrides={"autonomy": {"freeze": False}})
    paused = service.pause(enrolled.id)
    assert paused.status.value == "paused"
    resumed = service.resume(enrolled.id)
    assert resumed.status.value == "active"
    assert resumed.policy.autonomy.freeze is False


def test_reenrol_by_id_keeps_policy_unless_redetect_requested(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = init_git_repo(tmp_path / "kept", origin="https://github.com/acme/kept.git")
    enrolled = service.enrol(str(root), policy_overrides={"autonomy": {"freeze": False}})
    kept = service.reenrol(repo_id=enrolled.id)
    assert kept.id == enrolled.id
    assert kept.policy.autonomy.freeze is False
    redetected = service.reenrol(repo_id=enrolled.id, redetect=True)
    assert redetected.id == enrolled.id
    assert redetected.policy.autonomy.freeze is True


def test_enrol_refuses_runtime_directories_inside_the_tree(tmp_path: Path) -> None:
    root = init_git_repo(tmp_path / "inside", origin="https://github.com/acme/inside.git")
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(root / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(root / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    for directory in (paths.config, paths.logs):
        directory.mkdir(parents=True, exist_ok=True)
    database = Database(paths.database)
    conn = database.connect()
    service = RepositoryService(
        registry=SqliteRepositoryRegistry(conn),
        paths=paths,
        inspector=FilesystemGitInspector(),
        detector=ManifestStackDetector(),
        runtime=CacheRuntimeLayout(),
    )
    with pytest.raises(ValueError, match="outside"):
        service.enrol(str(root))
    assert not (root / "cache" / "worktrees").exists()


def test_symlink_or_junction_enrol_uses_one_stable_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    real = init_git_repo(tmp_path / "real-app", origin="https://github.com/acme/real-app.git")
    link = _directory_link(real, tmp_path / "links" / "alias-app")
    via_link = service.enrol(str(link), policy_overrides={"autonomy": {"freeze": False}})
    via_real = service.enrol(str(real))
    assert via_link.id == via_real.id
    assert via_link.id == stable_repository_id(str(real.resolve()))
    assert Path(via_real.realpath).resolve() == real.resolve()


@dataclass(frozen=True, slots=True)
class _Snap:
    git_root: Path
    realpath: Path
    origin: str | None
    current_branch: str
    default_branch: str


@dataclass(frozen=True, slots=True)
class _Stack:
    languages: tuple[str, ...]
    package_managers: tuple[str, ...]
    commands: Commands


class _FakeInspector:
    def __init__(self, root: Path) -> None:
        self._root = root

    def inspect(self, path: Path) -> _Snap:
        _ = path
        return _Snap(
            git_root=self._root,
            realpath=self._root,
            origin=None,
            current_branch="main",
            default_branch="main",
        )


class _FakeDetector:
    def detect(self, root: Path) -> _Stack:
        _ = root
        return _Stack(
            languages=("python",),
            package_managers=("pip",),
            commands=Commands(setup=(), test=(), lint=(), build=()),
        )


class _FakeRuntime:
    def __init__(self) -> None:
        self.ensured: list[tuple[str, str, str]] = []

    def worktree_root(self, cache_root: Path, repository_id: RepositoryId) -> Path:
        return cache_root / "worktrees" / repository_id.value

    def ensure_dirs(self, state_dir: Path, worktrees: Path, enrolled_root: Path) -> None:
        self.ensured.append((str(state_dir), str(worktrees), str(enrolled_root)))
        state_dir.mkdir(parents=True, exist_ok=True)
        worktrees.mkdir(parents=True, exist_ok=True)


def _directory_link(target: Path, link: Path) -> Path:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
        return link
    except OSError:
        if os.name != "nt":
            raise
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
        if result.returncode != 0:
            pytest.skip(f"cannot create directory link: {result.stderr or result.stdout}")
        return link
