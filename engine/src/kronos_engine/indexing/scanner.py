# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scan a git tree at a commit. Never execute repository files or write the tree."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.policy import RepositoryPolicy
from kronos_engine.indexing.languages import detect_language

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
_GENERATED_SUFFIXES = (".min.js", ".min.css", ".map")
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
_SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(aws_secret_access_key|api[_-]?secret)\s*[=:]\s*\S+"),
)


@dataclass(frozen=True, slots=True)
class ScannedFile:
    path: str
    text: str
    language: str


def scan_repository(
    git_root: Path,
    policy: RepositoryPolicy,
    *,
    commit: str | None = None,
) -> tuple[ScannedFile, ...]:
    root = git_root.resolve()
    if not policy.indexing.enabled:
        return ()
    sha = commit or _git_text(root, "rev-parse", "HEAD").strip()
    found: list[ScannedFile] = []
    for relative in _tracked_paths(root, sha):
        posix = relative.replace("\\", "/")
        if _should_skip_path(posix, policy.indexing.exclude_prefixes):
            continue
        size = _blob_size(root, sha, posix)
        if size is None or size > policy.indexing.max_file_bytes:
            continue
        payload = _blob_bytes(root, sha, posix)
        if payload is None or b"\x00" in payload[:8192]:
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if _looks_secret(posix, text):
            continue
        found.append(
            ScannedFile(path=posix, text=text, language=detect_language(posix))
        )
    return tuple(found)


def head_commit(git_root: Path) -> str:
    return _git_text(git_root.resolve(), "rev-parse", "HEAD").strip()


def diff_paths(
    git_root: Path, old_commit: str, new_commit: str
) -> tuple[tuple[str, str, str], ...]:
    """Return (status, path, renamed_from) tuples. status is A, M, D, or R."""
    raw = _git_bytes(
        git_root.resolve(),
        "diff",
        "--name-status",
        "--find-renames",
        "-z",
        old_commit,
        new_commit,
    )
    parts = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    changes: list[tuple[str, str, str]] = []
    index = 0
    while index < len(parts):
        status = parts[index]
        index += 1
        if status.startswith("R"):
            old = parts[index].replace("\\", "/")
            new = parts[index + 1].replace("\\", "/")
            index += 2
            changes.append(("R", new, old))
        elif status.startswith("C"):
            new = parts[index + 1].replace("\\", "/")
            index += 2
            changes.append(("A", new, ""))
        else:
            path = parts[index].replace("\\", "/")
            index += 1
            kind = status[0] if status else "M"
            changes.append((kind, path, ""))
    return tuple(changes)


def _should_skip_path(posix: str, exclude_prefixes: tuple[str, ...]) -> bool:
    lowered = posix.lower()
    name = posix.rsplit("/", 1)[-1].lower()
    if name in _SECRET_NAMES or name.endswith(".pem") or name.endswith(".key"):
        return True
    if any(lowered.endswith(suffix) for suffix in _GENERATED_SUFFIXES):
        return True
    suffix = Path(posix).suffix.lower()
    if suffix in _BINARY_SUFFIXES:
        return True
    parts = posix.split("/")
    if any(part in _VENDOR_PARTS for part in parts):
        return True
    for prefix in exclude_prefixes:
        if _matches_prefix(posix, prefix):
            return True
    return False


def _looks_secret(path: str, text: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    if name in _SECRET_NAMES or name.startswith(".env"):
        return True
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _matches_prefix(posix: str, prefix: str) -> bool:
    normalized = prefix.replace("\\", "/").lstrip("/")
    if not normalized:
        return False
    stripped = normalized.rstrip("/")
    if posix == stripped:
        return True
    return posix.startswith(stripped + "/")


def _tracked_paths(root: Path, commit: str) -> tuple[str, ...]:
    raw = _git_bytes(root, "ls-tree", "-r", "-z", "--name-only", commit)
    return tuple(item.decode("utf-8").replace("\\", "/") for item in raw.split(b"\0") if item)


def _blob_size(root: Path, commit: str, posix: str) -> int | None:
    try:
        raw = _git_text(root, "cat-file", "-s", f"{commit}:{posix}").strip()
    except GitReadError:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _blob_bytes(root: Path, commit: str, posix: str) -> bytes | None:
    try:
        return _git_bytes(root, "show", f"{commit}:{posix}")
    except GitReadError:
        return None


class GitReadError(RuntimeError):
    """Raised when a read-only git inspection command fails."""


_WRITE_VERBS = frozenset(
    {
        "commit",
        "push",
        "add",
        "merge",
        "rebase",
        "checkout",
        "switch",
        "reset",
        "rm",
        "mv",
        "worktree",
        "tag",
        "stash",
        "cherry-pick",
        "revert",
        "clean",
        "fetch",
        "pull",
        "clone",
        "init",
        "config",
        "remote",
    }
)


def _git_text(root: Path, *args: str) -> str:
    return _git_bytes(root, *args).decode("utf-8", errors="replace")


def _git_bytes(root: Path, *args: str) -> bytes:
    if args and args[0] in _WRITE_VERBS:
        raise GitReadError(f"git {args[0]} is forbidden while scanning")
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    with tempfile.TemporaryDirectory() as hooks:
        command = [
            "git",
            "-c",
            f"core.hooksPath={hooks}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "filter.lfs.smudge=",
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.required=false",
            "-C",
            str(root),
            *args,
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            shell=False,
            env=env,
        )
    if result.returncode != 0:
        raise GitReadError(result.stderr.decode("utf-8", errors="replace") or "git failed")
    return result.stdout
