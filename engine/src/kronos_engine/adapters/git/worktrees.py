# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task worktrees live under the application cache, never the enrolled tree."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.domain.entities import RepositoryId, TaskId


def repository_worktree_root(cache_root: Path, repository_id: RepositoryId) -> Path:
    return cache_root / "worktrees" / repository_id.value


def task_worktree(cache_root: Path, repository_id: RepositoryId, task_id: TaskId) -> Path:
    return repository_worktree_root(cache_root, repository_id) / task_id.value


def assert_outside_enrolled_tree(target: Path, enrolled_root: Path) -> None:
    resolved_target = target.resolve()
    resolved_root = enrolled_root.resolve()
    if resolved_target == resolved_root or resolved_root in resolved_target.parents:
        raise ValueError("worktrees must stay outside the enrolled git tree")
