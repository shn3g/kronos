# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer fetches the exact head and base independently."""

from __future__ import annotations

from pathlib import Path

from tests.support import BASE_SHA, HEAD_SHA, FakeGit

from kronos_reviewer.checkout import fetch_review_refs, materialize_head


def test_fetch_review_refs_fetches_head_and_base_independently() -> None:
    git = FakeGit()
    fetch_review_refs(git, head_sha=HEAD_SHA, base_sha=BASE_SHA)
    assert git.fetched == [HEAD_SHA, BASE_SHA] or set(git.fetched) == {HEAD_SHA, BASE_SHA}
    assert git.pushed == []


def test_materialize_head_writes_only_head_tree(tmp_path: Path) -> None:
    git = FakeGit()
    git.add(HEAD_SHA, "src/app.py", "print(1)\n")
    git.add(BASE_SHA, ".kronos/config.yaml", "schema_version: 2\n")
    worktree = materialize_head(git, head_sha=HEAD_SHA, dest=tmp_path / "sandbox")
    assert (worktree / "src" / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    assert not (worktree / ".kronos" / "config.yaml").exists()
