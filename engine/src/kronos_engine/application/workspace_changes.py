# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live git working-tree changes and user-initiated local commits. No push."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from kronos_engine.application.chat_diff import MAX_PATCH_CHARS, unified_write_patch
from kronos_engine.indexing.scanner import GitReadError, working_tree_changes

_STATUS_LABEL = {"A": "Added", "D": "Deleted", "M": "Modified", "R": "Renamed"}
_WRITE_VERBS = frozenset({"add", "commit", "restore"})
MAX_CHANGE_FILES = 200


def list_working_tree_changes(root: Path) -> list[dict[str, str]]:
    git_root = root.resolve()
    try:
        dirty = working_tree_changes(git_root)
    except GitReadError:
        return []
    items: list[dict[str, str]] = []
    for status, rel_path in dirty:
        if len(items) >= MAX_CHANGE_FILES:
            break
        posix = rel_path.replace("\\", "/")
        try:
            _posix_jail(git_root, posix)
        except ValueError:
            continue
        label = _STATUS_LABEL.get(status, "Modified")
        items.append(
            {
                "path": posix,
                "summary": f"{label} {posix}",
                "patch": _patch_for(git_root, status, posix),
                "status": status,
            }
        )
    return items


def mark_chat_writes(
    changes: Sequence[Mapping[str, str]],
    backup_paths: Sequence[str],
) -> list[dict[str, object]]:
    backups = {path.replace("\\", "/") for path in backup_paths}
    marked: list[dict[str, object]] = []
    for item in changes:
        row: dict[str, object] = dict(item)
        row["from_chat"] = str(item.get("path") or "").replace("\\", "/") in backups
        marked.append(row)
    return marked


def commit_working_tree(
    root: Path,
    message: str,
    paths: Sequence[str] | None = None,
) -> dict[str, object]:
    if message.strip() == "":
        raise ValueError("A commit message is required.")
    git_root = root.resolve()
    try:
        dirty = {path.replace("\\", "/") for _status, path in working_tree_changes(git_root)}
    except GitReadError as error:
        raise ValueError("There is nothing to commit.") from error
    requested = [path.replace("\\", "/") for path in paths] if paths is not None else sorted(dirty)
    chosen: list[str] = []
    seen: set[str] = set()
    for rel in requested:
        jailed = _posix_jail(git_root, rel)
        if jailed not in dirty or jailed in seen:
            continue
        seen.add(jailed)
        chosen.append(jailed)
    if not chosen:
        raise ValueError("There is nothing to commit.")
    _git_write(git_root, "add", "--", *chosen)
    _git_write(git_root, "commit", "-m", message.strip(), "--", *chosen)
    sha = _git_read(git_root, "rev-parse", "HEAD").strip()
    return {"ok": True, "sha": sha, "paths": chosen}


def restore_working_path(root: Path, rel_path: str) -> None:
    git_root = root.resolve()
    posix = _posix_jail(git_root, rel_path)
    try:
        status = {path.replace("\\", "/"): kind for kind, path in working_tree_changes(git_root)}
    except GitReadError as error:
        raise ValueError("No chat write to revert for that file.") from error
    kind = status.get(posix)
    if kind is None:
        raise ValueError("No chat write to revert for that file.")
    if kind == "A":
        target = (git_root / posix).resolve()
        if not _is_inside(git_root, target):
            raise ValueError("That path is outside the workspace or is not a file.")
        if target.is_file():
            target.unlink()
        return
    _git_write(
        git_root,
        "restore",
        "--source=HEAD",
        "--staged",
        "--worktree",
        "--",
        posix,
    )


def _patch_for(root: Path, status: str, posix: str) -> str:
    if status == "A":
        target = root / posix
        after = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        return _clip(unified_write_patch(path=posix, before="", after=after))
    try:
        patch = _git_read(root, "diff", "HEAD", "--", posix, allow_diff=True)
    except WorkspaceGitError:
        return ""
    return _clip(patch)


def _clip(patch: str) -> str:
    if len(patch) <= MAX_PATCH_CHARS:
        return patch
    return f"{patch[:MAX_PATCH_CHARS]}\n... truncated ..."


def _posix_jail(root: Path, rel_path: str) -> str:
    relative = Path(rel_path)
    if (
        rel_path.strip() == ""
        or relative.is_absolute()
        or any(part in {"..", ".git"} for part in relative.parts)
    ):
        raise ValueError("That path is outside the workspace or is not a file.")
    target = (root / relative).resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("That path is outside the workspace or is not a file.") from error


def _is_inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _git_read(root: Path, *args: str, allow_diff: bool = False) -> str:
    result = _run_git(root, args)
    if result.returncode == 0:
        return result.stdout
    if allow_diff and args[:1] == ("diff",) and result.returncode == 1:
        return result.stdout
    raise WorkspaceGitError(result.stderr.strip() or "git failed")


def _git_write(root: Path, *args: str) -> str:
    if not args or args[0] not in _WRITE_VERBS:
        raise WorkspaceGitError("that git command is not allowed")
    if "push" in args:
        raise WorkspaceGitError("Kronos does not push.")
    result = _run_git(root, args)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "git failed")
    return result.stdout


def _run_git(root: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    with tempfile.TemporaryDirectory() as hooks:
        return subprocess.run(
            [
                "git",
                "-c",
                f"core.hooksPath={hooks}",
                "-C",
                str(root),
                *args,
            ],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            env=env,
        )


class WorkspaceGitError(RuntimeError):
    """Raised when a read-only working-tree git command fails."""
