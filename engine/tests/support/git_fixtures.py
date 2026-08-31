# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import subprocess
from pathlib import Path


def init_git_repo(
    root: Path,
    *,
    files: dict[str, str] | None = None,
    origin: str | None = None,
    branch: str = "main",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _run(root, ["git", "init", "-b", branch])
    _run(root, ["git", "config", "user.email", "kronos-test@example.com"])
    _run(root, ["git", "config", "user.name", "Kronos Test"])
    _run(root, ["git", "config", "commit.gpgsign", "false"])
    for relative, content in (files or {"README.md": "fixture\n"}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _run(root, ["git", "add", "-A"])
    _run(root, ["git", "commit", "-m", "fixture"])
    if origin is not None:
        _run(root, ["git", "remote", "add", "origin", origin])
    return root


def _run(cwd: Path, argv: list[str]) -> None:
    result = subprocess.run(argv, cwd=cwd, check=False, capture_output=True, text=True, shell=False)
    if result.returncode != 0:
        raise RuntimeError(f"{argv} failed: {result.stderr}")
