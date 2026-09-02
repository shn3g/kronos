# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from kronos_engine.application.chat_revert import fold_workspace_diffs


def test_fold_workspace_diffs_keeps_the_latest_write_per_path() -> None:
    folded = fold_workspace_diffs(
        [
            ("git.wrote", {"repository_id": "repo_a", "path": "a.py", "patch": "+one\n"}),
            (
                "git.wrote",
                {
                    "repository_id": "repo_a",
                    "path": "a.py",
                    "summary": "Wrote a.py",
                    "patch": "+two\n",
                },
            ),
        ]
    )

    assert [item["path"] for item in folded] == ["a.py"]
    assert folded[0]["patch"] == "+two\n"
    assert folded[0]["summary"] == "Wrote a.py"


def test_fold_workspace_diffs_drops_reverted_paths() -> None:
    folded = fold_workspace_diffs(
        [
            ("git.wrote", {"repository_id": "repo_a", "path": "a.py", "patch": "+one\n"}),
            ("git.wrote", {"repository_id": "repo_a", "path": "b.py", "patch": "+two\n"}),
            ("git.reverted", {"repository_id": "repo_a", "path": "a.py"}),
        ]
    )

    assert [item["path"] for item in folded] == ["b.py"]


def test_fold_workspace_diffs_ignores_unrelated_events() -> None:
    folded = fold_workspace_diffs(
        [
            ("retrieval.searched", {"repository_id": "repo_a", "query": "hello"}),
            ("external.wrote", {"repository_id": "repo_a", "url": "https://example.test/a"}),
        ]
    )

    assert [item["path"] for item in folded] == ["https://example.test/a"]
