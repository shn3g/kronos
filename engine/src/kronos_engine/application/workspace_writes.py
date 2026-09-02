# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apply and undo desktop file writes inside an enrolled workspace. No push."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kronos_engine.application.chat_diff import unified_write_patch
from kronos_engine.application.workspace_changes import _posix_jail, restore_working_path

MAX_WRITE_CHARS = 200_000


class WorkspaceWriteTooLarge(ValueError):
    """Raised when the requested content is larger than a desktop write allows."""


@dataclass(frozen=True, slots=True)
class WorkspaceWrite:
    path: str
    summary: str
    patch: str


@dataclass(frozen=True, slots=True)
class WorkspaceRevert:
    path: str
    summary: str


class FileBackupStore(Protocol):
    def save_file_backup(
        self, repository_id: str, path: str, before: str, created_at: str
    ) -> None: ...

    def get_file_backup(self, repository_id: str, path: str) -> str | None: ...

    def delete_file_backup(self, repository_id: str, path: str) -> None: ...


def write_workspace_file(
    root: Path,
    repository_id: str,
    rel_path: str,
    content: str,
    *,
    backups: FileBackupStore,
    locked_prefixes: Sequence[str] = (),
    now: str,
) -> WorkspaceWrite:
    if len(content) > MAX_WRITE_CHARS:
        raise WorkspaceWriteTooLarge(
            f"File is too large to write here. Keep it under {MAX_WRITE_CHARS} characters."
        )
    git_root = root.resolve()
    posix = _posix_jail(git_root, rel_path)
    if _is_locked(posix, locked_prefixes):
        raise ValueError("That path is locked by repository policy.")
    target = git_root / posix
    target.parent.mkdir(parents=True, exist_ok=True)
    before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    backups.save_file_backup(repository_id, posix, before, now)
    target.write_text(content, encoding="utf-8")
    return WorkspaceWrite(
        path=posix,
        summary=f"Wrote {posix}",
        patch=unified_write_patch(path=posix, before=before, after=content),
    )


def revert_workspace_write(
    root: Path,
    repository_id: str,
    rel_path: str,
    *,
    backups: FileBackupStore,
) -> WorkspaceRevert:
    git_root = root.resolve()
    posix = _posix_jail(git_root, rel_path)
    before = backups.get_file_backup(repository_id, posix)
    if before is None:
        restore_working_path(git_root, posix)
        return WorkspaceRevert(path=posix, summary=f"Reverted {posix}")
    target = git_root / posix
    if before == "":
        if target.is_file():
            target.unlink()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(before, encoding="utf-8")
    backups.delete_file_backup(repository_id, posix)
    return WorkspaceRevert(path=posix, summary=f"Reverted {posix}")


def forget_workspace_backups(
    backups: FileBackupStore, repository_id: str, paths: Sequence[str]
) -> None:
    for rel_path in paths:
        backups.delete_file_backup(repository_id, Path(rel_path).as_posix())


def _is_locked(posix: str, locked_prefixes: Sequence[str]) -> bool:
    return any(
        posix == prefix.rstrip("/") or posix.startswith(prefix) for prefix in locked_prefixes
    )
