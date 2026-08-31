# SPDX-License-Identifier: AGPL-3.0-or-later
"""Enrol repositories, preview policy files, and isolate per-repo state."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from kronos_engine.adapters.git.detection import detect_stack
from kronos_engine.adapters.git.repository import inspect_git
from kronos_engine.adapters.git.worktrees import repository_worktree_root
from kronos_engine.config.paths import KronosPaths
from kronos_engine.config.repository import EnrolmentPreview, github_owner, render_enrolment_preview
from kronos_engine.domain.entities import EnrolledRepository, RepositoryId, RepositoryStatus
from kronos_engine.domain.policy import (
    RepositoryPolicy,
    apply_model_proposal,
    default_policy,
    parse_policy,
    policy_to_dict,
)
from kronos_engine.ports.repository import RepositoryRegistry


class RepositoryNotFound(LookupError):
    """Raised when a repository id is unknown. Never returns another repo's data."""


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    state_dir: str
    worktrees: str


@dataclass(frozen=True, slots=True)
class InspectResult:
    git_root: str
    origin: str | None
    current_branch: str
    default_branch: str
    languages: tuple[str, ...]
    package_managers: tuple[str, ...]
    policy: RepositoryPolicy
    preview: EnrolmentPreview
    wrote_files: bool = False
    committed: bool = False
    pushed: bool = False


class RepositoryService:
    def __init__(self, registry: RepositoryRegistry, paths: KronosPaths) -> None:
        self._registry = registry
        self._paths = paths

    def inspect(self, path: str) -> InspectResult:
        snapshot = inspect_git(Path(path))
        stack = detect_stack(snapshot.git_root)
        policy = default_policy(
            integration_branch=snapshot.default_branch,
            protected_branch=snapshot.default_branch,
        )
        policy = replace(
            policy,
            commands=stack.commands,
        )
        preview = render_enrolment_preview(
            snapshot.git_root,
            policy,
            github_owner(snapshot.origin),
        )
        return InspectResult(
            git_root=str(snapshot.realpath),
            origin=snapshot.origin,
            current_branch=snapshot.current_branch,
            default_branch=snapshot.default_branch,
            languages=stack.languages,
            package_managers=stack.package_managers,
            policy=policy,
            preview=preview,
            wrote_files=False,
            committed=False,
            pushed=False,
        )

    def enrol(
        self,
        path: str,
        policy_overrides: Mapping[str, object] | None = None,
    ) -> EnrolledRepository:
        inspection = self.inspect(path)
        policy = inspection.policy
        if policy_overrides:
            policy = parse_policy(_deep_merge(policy_to_dict(policy), dict(policy_overrides)))
        realpath = inspection.git_root
        repo_id = stable_repository_id(realpath)
        existing = self._registry.get(repo_id) or self._registry.get_by_realpath(realpath)
        enrolled_at = existing.enrolled_at if existing is not None else _now()
        record = EnrolledRepository(
            id=repo_id,
            realpath=realpath,
            origin=inspection.origin,
            display_name=Path(realpath).name,
            status=RepositoryStatus.ACTIVE,
            policy=policy,
            enrolled_at=enrolled_at,
        )
        self._registry.save(record)
        self._ensure_runtime(record.id)
        return record

    def list(self) -> Sequence[EnrolledRepository]:
        return self._registry.list()

    def get(self, repo_id: RepositoryId) -> EnrolledRepository:
        found = self._registry.get(repo_id)
        if found is None:
            raise RepositoryNotFound(repo_id.value)
        return found

    def pause(self, repo_id: RepositoryId) -> EnrolledRepository:
        return self._set_status(repo_id, RepositoryStatus.PAUSED)

    def disable(self, repo_id: RepositoryId) -> EnrolledRepository:
        return self._set_status(repo_id, RepositoryStatus.DISABLED)

    def remove(self, repo_id: RepositoryId) -> None:
        record = self.get(repo_id)
        self._registry.delete(record.id)
        state_dir = Path(self.runtime_paths(record.id).state_dir)
        if state_dir.is_dir():
            shutil.rmtree(state_dir)

    def reenrol(
        self,
        repo_id: RepositoryId | None = None,
        path: str | None = None,
    ) -> EnrolledRepository:
        if path is not None:
            return self.enrol(path)
        if repo_id is None:
            raise ValueError("reenrol requires a path or repository id")
        record = self.get(repo_id)
        return self.enrol(record.realpath)

    def apply_model_policy(
        self,
        repo_id: RepositoryId,
        proposal: Mapping[str, object],
    ) -> EnrolledRepository:
        current = self.get(repo_id)
        policy = apply_model_proposal(current.policy, proposal)
        updated = replace(current, policy=policy)
        self._registry.save(updated)
        return updated

    def runtime_paths(self, repo_id: RepositoryId) -> RuntimePaths:
        state_dir = self._paths.data / "repositories" / repo_id.value
        worktrees = repository_worktree_root(self._paths.cache, repo_id)
        return RuntimePaths(state_dir=str(state_dir), worktrees=str(worktrees))

    def _set_status(self, repo_id: RepositoryId, status: RepositoryStatus) -> EnrolledRepository:
        current = self.get(repo_id)
        updated = replace(current, status=status)
        self._registry.save(updated)
        return updated

    def _ensure_runtime(self, repo_id: RepositoryId) -> None:
        runtime = self.runtime_paths(repo_id)
        Path(runtime.state_dir).mkdir(parents=True, exist_ok=True)
        Path(runtime.worktrees).mkdir(parents=True, exist_ok=True)


def stable_repository_id(realpath: str) -> RepositoryId:
    normalized = realpath.replace("\\", "/").casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return RepositoryId(f"repo_{digest}")


def _deep_merge(base: dict[str, object], override: Mapping[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()
