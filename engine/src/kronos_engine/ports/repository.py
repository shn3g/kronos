# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repository registry and git inspector ports. Application depends on these."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kronos_engine.domain.entities import EnrolledRepository, RepositoryId
from kronos_engine.domain.policy import Commands


class RuntimeInsideEnrolledTree(ValueError):
    """Raised when runtime state would be created inside an enrolled git tree."""


@dataclass(frozen=True, slots=True)
class GitSnapshot:
    git_root: Path
    realpath: Path
    origin: str | None
    current_branch: str
    default_branch: str


@dataclass(frozen=True, slots=True)
class StackDetection:
    languages: tuple[str, ...]
    package_managers: tuple[str, ...]
    commands: Commands


class RepositoryRegistry(Protocol):
    def get(self, repo_id: RepositoryId) -> EnrolledRepository | None: ...

    def get_by_realpath(self, realpath: str) -> EnrolledRepository | None: ...

    def list(self) -> Sequence[EnrolledRepository]: ...

    def save(self, repo: EnrolledRepository) -> None: ...

    def delete(self, repo_id: RepositoryId) -> None: ...


class GitInspector(Protocol):
    def inspect(self, path: Path) -> GitSnapshot: ...


class StackDetector(Protocol):
    def detect(self, root: Path) -> StackDetection: ...


class RuntimeLayout(Protocol):
    def worktree_root(self, cache_root: Path, repository_id: RepositoryId) -> Path: ...

    def ensure_dirs(self, state_dir: Path, worktrees: Path, enrolled_root: Path) -> None: ...
