# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo

from kronos_engine.application.workspace_files import list_workspace_files, read_workspace_file


def test_list_workspace_files_includes_tracked_and_untracked(tmp_path: Path) -> None:
    repo = init_git_repo(
        tmp_path / "alpha",
        files={"README.md": "hello\n", "src/app.py": "print(1)\n"},
    )
    (repo / "src" / "new.py").write_text("print(2)\n", encoding="utf-8")

    paths = {item["path"] for item in list_workspace_files(repo)}

    assert "README.md" in paths
    assert "src/app.py" in paths
    assert "src/new.py" in paths
    assert not any(path.startswith(".git") for path in paths)


def test_read_workspace_file_returns_text_and_rejects_escapes(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"src/app.py": "print(1)\n"})

    payload = read_workspace_file(repo, "src/app.py")

    assert payload["path"] == "src/app.py"
    assert payload["content"] == "print(1)\n"
    assert payload["binary"] is False

    with pytest.raises(ValueError, match="outside"):
        read_workspace_file(repo, "../secret.txt")


def test_read_workspace_file_rejects_missing_paths(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n"})

    with pytest.raises(ValueError, match="not a file"):
        read_workspace_file(repo, "missing.py")


def test_list_workspace_files_skips_vendor_and_secret_paths(tmp_path: Path) -> None:
    repo = init_git_repo(
        tmp_path / "alpha",
        files={
            "src/app.py": "print(1)\n",
            "node_modules/pkg/index.js": "module.exports = 1\n",
            ".env": "SECRET=1\n",
        },
    )

    paths = {item["path"] for item in list_workspace_files(repo)}

    assert "src/app.py" in paths
    assert "node_modules/pkg/index.js" not in paths
    assert ".env" not in paths


def test_read_workspace_file_marks_binary_and_hides_secrets(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n", ".env": "SECRET=1\n"})
    (repo / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    payload = read_workspace_file(repo, "icon.png")

    assert payload["path"] == "icon.png"
    assert payload["binary"] is True
    assert payload["content"] == ""

    with pytest.raises(ValueError, match="outside"):
        read_workspace_file(repo, ".env")
