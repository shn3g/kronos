# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only git inspection. Never commit or push."""

from __future__ import annotations

import subprocess
from pathlib import Path

from kronos_engine.ports.repository import GitSnapshot

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
_ALLOWED_REMOTE = frozenset({("remote", "get-url", "origin")})


class GitError(ValueError):
    """Raised when a path is not a git work tree or git fails."""


class GitWriteForbidden(RuntimeError):
    """Enrolment must not mutate git history or remotes."""


class FilesystemGitInspector:
    def inspect(self, path: Path) -> GitSnapshot:
        return inspect_git(path)


def inspect_git(path: Path) -> GitSnapshot:
    start = path.expanduser()
    if not start.exists():
        raise GitError("path does not exist")
    root = Path(
        _git(start, "rev-parse", "--show-toplevel").strip()
    ).resolve()
    origin = _optional_git(root, "remote", "get-url", "origin")
    current = _git(root, "branch", "--show-current").strip() or "main"
    default = _default_branch(root) or current
    return GitSnapshot(
        git_root=root,
        realpath=root,
        origin=origin,
        current_branch=current,
        default_branch=default,
    )


def resolve_git_realpath(path: Path) -> Path:
    return inspect_git(path).realpath


def _default_branch(root: Path) -> str | None:
    raw = _optional_git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if raw is None:
        raw = _optional_git(root, "rev-parse", "--abbrev-ref", "origin/HEAD")
    if raw is None:
        return None
    name = raw.strip()
    if name.startswith("refs/remotes/origin/"):
        return name.rsplit("/", 1)[-1]
    if name.startswith("origin/"):
        return name.split("/", 1)[1]
    return name or None


def _optional_git(cwd: Path, *args: str) -> str | None:
    try:
        value = _git(cwd, *args).strip()
    except GitError:
        return None
    return value or None


def _git(cwd: Path, *args: str) -> str:
    _assert_read_only(args)
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "not a git repository")
    return result.stdout


def _assert_read_only(args: tuple[str, ...]) -> None:
    if args in _ALLOWED_REMOTE:
        return
    if args and args[0] in _WRITE_VERBS:
        raise GitWriteForbidden(f"git {' '.join(args)} is forbidden during enrolment")
