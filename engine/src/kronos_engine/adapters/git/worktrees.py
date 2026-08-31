# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task worktrees live under the application cache, never the enrolled tree."""

from __future__ import annotations

import subprocess
from pathlib import Path

from kronos_engine.domain.entities import RepositoryId, TaskId
from kronos_engine.ports.repository import RuntimeInsideEnrolledTree


def repository_worktree_root(cache_root: Path, repository_id: RepositoryId) -> Path:
    return cache_root / "worktrees" / repository_id.value


def task_worktree(cache_root: Path, repository_id: RepositoryId, task_id: TaskId) -> Path:
    return repository_worktree_root(cache_root, repository_id) / task_id.value


class CacheRuntimeLayout:
    def worktree_root(self, cache_root: Path, repository_id: RepositoryId) -> Path:
        return repository_worktree_root(cache_root, repository_id)

    def ensure_dirs(self, state_dir: Path, worktrees: Path, enrolled_root: Path) -> None:
        assert_outside_enrolled_tree(state_dir, enrolled_root)
        assert_outside_enrolled_tree(worktrees, enrolled_root)
        state_dir.mkdir(parents=True, exist_ok=True)
        worktrees.mkdir(parents=True, exist_ok=True)


class GitCacheWorktree:
    def create(
        self,
        enrolled_root: Path,
        cache_root: Path,
        repository_id: RepositoryId,
        task_id: TaskId,
    ) -> Path:
        target = task_worktree(cache_root, repository_id, task_id)
        assert_outside_enrolled_tree(target, enrolled_root)
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), "HEAD"],
            cwd=enrolled_root,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"worktree create failed: {result.stderr}")
        return target


def assert_outside_enrolled_tree(target: Path, enrolled_root: Path) -> None:
    resolved_target = target.resolve()
    resolved_root = enrolled_root.resolve()
    if resolved_target == resolved_root or resolved_root in resolved_target.parents:
        raise RuntimeInsideEnrolledTree("worktrees must stay outside the enrolled git tree")
