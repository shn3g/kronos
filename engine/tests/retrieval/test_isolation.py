# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests.retrieval.support import indexing_policy, kronos_paths
from tests.support.git_fixtures import init_git_repo

from kronos_engine.indexing.service import IndexingService


def test_two_repository_indexes_never_cross_contaminate(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    alpha_root = init_git_repo(
        tmp_path / "alpha",
        files={"src/alpha_only.py": "def alpha_marker():\n    return 'ALPHA_UNIQUE_TOKEN'\n"},
    )
    beta_root = init_git_repo(
        tmp_path / "beta",
        files={"src/beta_only.py": "def beta_marker():\n    return 'BETA_UNIQUE_TOKEN'\n"},
    )
    service = IndexingService(paths)
    policy = indexing_policy()
    service.rebuild("repo_alpha", alpha_root, policy)
    service.rebuild("repo_beta", beta_root, policy)

    alpha_hits = service.search("repo_alpha", "ALPHA_UNIQUE_TOKEN")
    beta_hits = service.search("repo_beta", "BETA_UNIQUE_TOKEN")
    assert any("alpha_only.py" in item.path for item in alpha_hits.items)
    assert any("beta_only.py" in item.path for item in beta_hits.items)
    assert not any("BETA_UNIQUE_TOKEN" in item.text for item in alpha_hits.items)
    assert not any("ALPHA_UNIQUE_TOKEN" in item.text for item in beta_hits.items)
    assert not any("beta_only.py" in item.path for item in alpha_hits.items)
    assert not any("alpha_only.py" in item.path for item in beta_hits.items)

    leaked = service.search("repo_alpha", "BETA_UNIQUE_TOKEN")
    assert leaked.items == ()
    alpha_dir = paths.cache / "indexes" / "repo_alpha"
    beta_dir = paths.cache / "indexes" / "repo_beta"
    assert alpha_dir.is_dir()
    assert beta_dir.is_dir()
    assert alpha_dir != beta_dir
    assert alpha_root.resolve() not in alpha_dir.resolve().parents
    assert list(alpha_root.glob("*.sqlite*")) == []
    assert list(beta_root.glob("*.sqlite*")) == []
