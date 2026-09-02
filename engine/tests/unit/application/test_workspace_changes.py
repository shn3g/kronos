# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo

from kronos_engine.application.workspace_changes import (
    commit_working_tree,
    list_working_tree_changes,
    mark_chat_writes,
    restore_working_path,
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def test_list_changes_includes_modified_and_untracked_files(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    (repo / "hello.py").write_text("new\n", encoding="utf-8")
    (repo / "fresh.py").write_text("hi\n", encoding="utf-8")

    changes = list_working_tree_changes(repo)
    by_path = {item["path"]: item for item in changes}

    assert "-old" in str(by_path["hello.py"]["patch"])
    assert "+new" in str(by_path["hello.py"]["patch"])
    assert "Modified" in str(by_path["hello.py"]["summary"])
    assert "+hi" in str(by_path["fresh.py"]["patch"])
    assert "Added" in str(by_path["fresh.py"]["summary"])


def test_list_changes_includes_deleted_files(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"gone.py": "bye\n"})
    (repo / "gone.py").unlink()

    changes = list_working_tree_changes(repo)

    assert changes[0]["path"] == "gone.py"
    assert "Deleted" in str(changes[0]["summary"])
    assert "-bye" in str(changes[0]["patch"])


def test_commit_records_dirty_files_and_clears_the_list(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    (repo / "hello.py").write_text("new\n", encoding="utf-8")

    result = commit_working_tree(repo, "Fix hello.py", ["hello.py"])

    assert result["ok"] is True
    assert result["paths"] == ["hello.py"]
    assert result["sha"]
    assert list_working_tree_changes(repo) == []
    assert _git(repo, "log", "-1", "--pretty=%s").strip() == "Fix hello.py"
    assert (repo / "hello.py").read_text(encoding="utf-8") == "new\n"


def test_commit_rejects_empty_message_and_clean_trees(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})

    with pytest.raises(ValueError, match="message"):
        commit_working_tree(repo, "   ", ["hello.py"])

    with pytest.raises(ValueError, match="nothing"):
        commit_working_tree(repo, "Empty", ["hello.py"])


def test_commit_rejects_paths_outside_the_workspace(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    (repo / "hello.py").write_text("new\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        commit_working_tree(repo, "Escape", ["../secret.txt"])


def test_commit_refuses_a_push_verb(tmp_path: Path) -> None:
    from kronos_engine.application.workspace_changes import WorkspaceGitError, _git_write

    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})

    with pytest.raises(WorkspaceGitError, match="not allowed"):
        _git_write(repo, "push", "origin", "main")


def test_restore_working_path_resets_a_dirty_file_to_head(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    (repo / "hello.py").write_text("local\n", encoding="utf-8")

    restore_working_path(repo, "hello.py")

    assert (repo / "hello.py").read_text(encoding="utf-8") == "old\n"
    assert list_working_tree_changes(repo) == []


def test_restore_working_path_deletes_an_untracked_file(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    (repo / "fresh.py").write_text("hi\n", encoding="utf-8")

    restore_working_path(repo, "fresh.py")

    assert not (repo / "fresh.py").exists()


def test_mark_chat_writes_flags_only_backup_paths() -> None:
    changes = [
        {"path": "hello.py", "summary": "Modified hello.py", "patch": "+new\n", "status": "M"},
        {"path": "other.py", "summary": "Added other.py", "patch": "+x\n", "status": "A"},
    ]

    marked = mark_chat_writes(changes, ("hello.py",))

    assert marked[0]["from_chat"] is True
    assert marked[1]["from_chat"] is False
    assert marked[0]["path"] == "hello.py"
