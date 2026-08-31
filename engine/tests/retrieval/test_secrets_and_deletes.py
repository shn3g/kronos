# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests.retrieval.support import (
    delete_and_commit,
    golden_fixture,
    indexing_policy,
    kronos_paths,
    rename_and_commit,
    write_and_commit,
)
from tests.support.git_fixtures import init_git_repo

from kronos_engine.indexing.service import IndexingService


def test_secrets_never_appear_in_retrieved_context(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = golden_fixture(tmp_path / "secret-repo")
    service = IndexingService(paths)
    service.rebuild("repo_secret", root, indexing_policy())
    for query in ("AKIAIOSFODNN7EXAMPLE", "ghp_exampletokenvalueexampletoken12", "AWS_ACCESS_KEY"):
        pack = service.search("repo_secret", query)
        blob = "\n".join(item.text for item in pack.items)
        assert "AKIAIOSFODNN7EXAMPLE" not in blob
        assert "ghp_exampletokenvalueexampletoken12" not in blob
        assert not any(item.path.endswith("secrets.env") for item in pack.items)


def test_secret_patterns_past_50k_in_source_are_not_searchable(tmp_path: Path) -> None:
    padding = "safe_padding = 1\n" + ("x" * 51_000) + "\n"
    body = (
        padding
        + "AKIAIOSFODNN7EXAMPLE\n"
        + "-----BEGIN PRIVATE KEY-----\n"
        + "ghp_lateTokenValueExampleToken99\n"
        + "VISIBLE_AFTER_PAD = 1\n"
    )
    paths = kronos_paths(tmp_path)
    root = init_git_repo(tmp_path / "late-secret", files={"src/mod.py": body})
    service = IndexingService(paths)
    service.rebuild("repo_late", root, indexing_policy())
    blob = "\n".join(
        item.text
        for query in (
            "AKIAIOSFODNN7EXAMPLE",
            "BEGIN PRIVATE KEY",
            "ghp_lateTokenValueExampleToken99",
            "VISIBLE_AFTER_PAD",
        )
        for item in service.search("repo_late", query).items
    )
    assert "AKIAIOSFODNN7EXAMPLE" not in blob
    assert "BEGIN PRIVATE KEY" not in blob
    assert "ghp_lateTokenValueExampleToken99" not in blob
    assert service.search("repo_late", "VISIBLE_AFTER_PAD").items == ()


def test_deleted_chunks_disappear_from_search(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "churn",
        files={
            "src/keep.py": "def keep():\n    return 1\n",
            "src/gone.py": "TOKEN_DELETE_ME = 1\n",
        },
    )
    service = IndexingService(paths)
    policy = indexing_policy()
    service.rebuild("repo_churn", root, policy)
    found = service.search("repo_churn", "TOKEN_DELETE_ME")
    assert any(item.path.endswith("gone.py") for item in found.items)

    delete_and_commit(root, "src/gone.py", "remove gone")
    service.incremental("repo_churn", root, policy)
    missing = service.search("repo_churn", "TOKEN_DELETE_ME")
    assert missing.items == ()
    assert not any("gone.py" in item.path for item in missing.items)
    kept = service.search("repo_churn", "keep")
    assert any(item.path.endswith("keep.py") for item in kept.items)


def test_rename_moves_chunks_to_the_new_path(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "rename",
        files={"src/old_name.py": "TOKEN_RENAMED_SYMBOL = True\n"},
    )
    service = IndexingService(paths)
    policy = indexing_policy()
    service.rebuild("repo_rename", root, policy)
    rename_and_commit(root, "src/old_name.py", "src/new_name.py", "rename module")
    service.incremental("repo_rename", root, policy)
    hits = service.search("repo_rename", "TOKEN_RENAMED_SYMBOL")
    assert any(item.path.endswith("new_name.py") for item in hits.items)
    assert not any(item.path.endswith("old_name.py") for item in hits.items)


def test_changed_file_replaces_previous_chunks(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "edit",
        files={"src/mod.py": "OLD_TOKEN_VALUE = 1\n"},
    )
    service = IndexingService(paths)
    policy = indexing_policy()
    service.rebuild("repo_edit", root, policy)
    write_and_commit(root, {"src/mod.py": "NEW_TOKEN_VALUE = 2\n"}, "edit module")
    service.incremental("repo_edit", root, policy)
    assert service.search("repo_edit", "OLD_TOKEN_VALUE").items == ()
    hits = service.search("repo_edit", "NEW_TOKEN_VALUE")
    assert any(item.path.endswith("mod.py") for item in hits.items)
