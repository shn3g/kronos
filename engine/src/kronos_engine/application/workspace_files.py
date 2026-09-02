# SPDX-License-Identifier: AGPL-3.0-or-later
"""List and read workspace files for the desktop Files tree. Read-only."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from kronos_engine.application.workspace_changes import (
    WorkspaceGitError,
    _git_read,
    _posix_jail,
)

MAX_WORKSPACE_FILES = 2000
MAX_FILE_CHARS = 200_000
_VENDOR_PARTS = frozenset(
    {
        "node_modules",
        "vendor",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".venv",
        "venv",
        "third_party",
        ".git",
        ".tox",
        "site-packages",
    }
)
_SECRET_NAMES = frozenset(
    {
        "secrets.env",
        ".env",
        "credentials.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)
_BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".whl",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".wasm",
        ".bin",
        ".pyc",
        ".pyo",
        ".class",
        ".o",
        ".a",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
    }
)


class WorkspaceFileEntry(TypedDict):
    path: str


class WorkspaceFileContents(TypedDict):
    path: str
    content: str
    binary: bool


def list_workspace_files(root: Path) -> list[WorkspaceFileEntry]:
    git_root = root.resolve()
    try:
        raw = _git_read(
            git_root,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        )
    except WorkspaceGitError:
        return []
    listed: list[WorkspaceFileEntry] = []
    seen: set[str] = set()
    for item in raw.split("\0"):
        if item == "":
            continue
        posix = item.replace("\\", "/")
        if _skip_listed_path(posix):
            continue
        try:
            jailed = _posix_jail(git_root, posix)
        except ValueError:
            continue
        if jailed in seen:
            continue
        seen.add(jailed)
        listed.append({"path": jailed})
        if len(listed) >= MAX_WORKSPACE_FILES:
            break
    listed.sort(key=lambda entry: entry["path"])
    return listed


def read_workspace_file(root: Path, rel_path: str) -> WorkspaceFileContents:
    git_root = root.resolve()
    posix = _posix_jail(git_root, rel_path)
    if _is_secret_path(posix):
        raise ValueError("That path is outside the workspace or is not a file.")
    target = git_root / posix
    if not target.is_file():
        raise ValueError("That path is outside the workspace or is not a file.")
    if _is_binary_path(posix) or _file_has_nul(target):
        return {"path": posix, "content": "", "binary": True}
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_FILE_CHARS:
        text = f"{text[:MAX_FILE_CHARS]}\n... truncated ..."
    return {"path": posix, "content": text, "binary": False}


def _skip_listed_path(posix: str) -> bool:
    if _is_secret_path(posix):
        return True
    return any(part in _VENDOR_PARTS for part in posix.split("/"))


def _is_secret_path(posix: str) -> bool:
    name = posix.rsplit("/", 1)[-1].lower()
    if name in _SECRET_NAMES or name.startswith(".env"):
        return True
    return name.endswith(".pem") or name.endswith(".key")


def _is_binary_path(posix: str) -> bool:
    suffix = Path(posix).suffix.lower()
    return suffix in _BINARY_SUFFIXES


def _file_has_nul(target: Path) -> bool:
    sample = target.read_bytes()[:8192]
    return b"\x00" in sample
