# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from kronos_engine.adapters.git.worktrees import (
    assert_outside_enrolled_tree,
    repository_worktree_root,
)
from kronos_engine.domain.entities import RepositoryId


def test_worktrees_live_under_cache_not_the_repo(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    enrolled = tmp_path / "repo"
    enrolled.mkdir()
    path = repository_worktree_root(cache, RepositoryId("repo_abc"))
    assert path == cache / "worktrees" / "repo_abc"
    assert enrolled not in path.parents
    assert path != enrolled


def test_assert_outside_enrolled_tree_rejects_nested_paths(tmp_path: Path) -> None:
    enrolled = tmp_path / "repo"
    enrolled.mkdir()
    nested = enrolled / "cache" / "worktrees"
    with pytest.raises(ValueError, match="outside"):
        assert_outside_enrolled_tree(nested, enrolled)
    assert_outside_enrolled_tree(tmp_path / "cache" / "worktrees", enrolled)
