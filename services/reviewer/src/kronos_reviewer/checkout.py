# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetch exact head and base independently. Policy files come from base elsewhere."""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Protocol


class ReviewGit(Protocol):
    def fetch_sha(self, sha: str) -> None: ...

    def show_file(self, sha: str, path: str) -> str: ...

    def changed_files(self, base_sha: str, head_sha: str) -> tuple[str, ...]: ...

    def export_tree(self, sha: str, dest: Path) -> None: ...


def fetch_review_refs(git: ReviewGit, *, head_sha: str, base_sha: str) -> None:
    git.fetch_sha(head_sha)
    git.fetch_sha(base_sha)


def materialize_head(git: ReviewGit, *, head_sha: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    git.export_tree(head_sha, dest)
    return dest


class GitInstallationFetch:
    """Git fetch of exact SHAs using the reviewer installation token."""

    def __init__(self, *, remote_url: str, token: str, store: Path) -> None:
        self._remote = remote_url
        self._token = token
        self._store = store
        self._store.mkdir(parents=True, exist_ok=True)
        if not (self._store / ".git").exists():
            subprocess.run(
                ["git", "init"],
                cwd=self._store,
                check=True,
                capture_output=True,
            )

    def fetch_args(self, sha: str) -> tuple[str, ...]:
        return (
            "git",
            "-c",
            f"http.extraheader=AUTHORIZATION: bearer {self._token}",
            "fetch",
            "--depth=1",
            self._remote,
            sha,
        )

    def fetch_sha(self, sha: str) -> None:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        subprocess.run(
            list(self.fetch_args(sha)),
            cwd=self._store,
            check=True,
            capture_output=True,
            env=env,
        )

    def show_file(self, sha: str, path: str) -> str:
        completed = subprocess.run(
            ["git", "show", f"{sha}:{path}"],
            cwd=self._store,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout

    def changed_files(self, base_sha: str, head_sha: str) -> tuple[str, ...]:
        completed = subprocess.run(
            ["git", "diff", "--name-only", base_sha, head_sha],
            cwd=self._store,
            check=True,
            capture_output=True,
            text=True,
        )
        return tuple(line for line in completed.stdout.splitlines() if line)

    def export_tree(self, sha: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(
            ["git", "archive", sha],
            cwd=self._store,
            check=True,
            capture_output=True,
        )
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            tar.extractall(dest, filter="data")
