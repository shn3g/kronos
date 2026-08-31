# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetch exact head and base independently. Policy files come from base elsewhere."""

from __future__ import annotations

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
