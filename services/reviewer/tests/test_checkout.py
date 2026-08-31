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


def test_installation_fetch_retrieves_shas_with_reviewer_token(tmp_path: Path) -> None:
    import subprocess

    from kronos_reviewer.checkout import GitInstallationFetch, fetch_review_refs

    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init"], cwd=origin, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-m",
            "base",
        ],
        cwd=origin,
        check=True,
        capture_output=True,
    )
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=origin, text=True).strip()
    (origin / "head.txt").write_text("head\n", encoding="utf-8")
    subprocess.run(["git", "add", "head.txt"], cwd=origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "head"],
        cwd=origin,
        check=True,
        capture_output=True,
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=origin, text=True).strip()
    store = tmp_path / "store"
    git = GitInstallationFetch(
        remote_url=str(origin),
        token="ghs_fixture_reviewer",
        store=store,
    )
    fetch_review_refs(git, head_sha=head, base_sha=base)
    assert "ghs_fixture_reviewer" in " ".join(git.fetch_args(head))
    dest = tmp_path / "wt"
    git.export_tree(head, dest)
    assert (dest / "head.txt").read_text(encoding="utf-8") == "head\n"


def test_materialize_head_writes_only_head_tree(tmp_path: Path) -> None:
    git = FakeGit()
    git.add(HEAD_SHA, "src/app.py", "print(1)\n")
    git.add(BASE_SHA, ".kronos/config.yaml", "schema_version: 2\n")
    worktree = materialize_head(git, head_sha=HEAD_SHA, dest=tmp_path / "sandbox")
    assert (worktree / "src" / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    assert not (worktree / ".kronos" / "config.yaml").exists()
