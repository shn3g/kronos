# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tests.retrieval.support import golden_fixture, indexing_policy
from tests.support.git_fixtures import init_git_repo

from kronos_engine.indexing.scanner import scan_repository


def test_scanner_respects_gitignore_vendor_size_binary_and_secrets(tmp_path: Path) -> None:
    root = golden_fixture(tmp_path / "repo")
    files = scan_repository(root, indexing_policy())
    paths = {item.path for item in files}

    assert "pkg/db.py" in paths
    assert "docs/overview.md" in paths
    assert "web/client.ts" in paths
    assert "ignored.txt" not in paths
    assert "vendor/jquery.min.js" not in paths
    assert "node_modules/leftpad/index.js" not in paths
    assert "secrets.env" not in paths
    assert "binary.bin" not in paths
    assert "huge.txt" not in paths
    assert not any("AKIAIOSFODNN7EXAMPLE" in item.text for item in files)
    assert not any("SHOULD_NOT_BE_INDEXED_TOKEN" in item.text for item in files)


def test_exclude_prefixes_match_path_boundaries(tmp_path: Path) -> None:
    root = init_git_repo(
        tmp_path / "prefix",
        files={
            "src/mod.py": "SRC_ONLY = 1\n",
            "srcfoo/mod.py": "BOUNDARY_KEEP = 1\n",
        },
    )
    policy = indexing_policy()
    policy = replace(
        policy,
        indexing=replace(policy.indexing, exclude_prefixes=("src",)),
    )
    paths = {item.path for item in scan_repository(root, policy)}
    assert "src/mod.py" not in paths
    assert "srcfoo/mod.py" in paths


def test_scanner_does_not_write_into_the_enrolled_tree(tmp_path: Path) -> None:
    root = golden_fixture(tmp_path / "repo")
    before = {path.relative_to(root) for path in root.rglob("*") if path.is_file()}
    scan_repository(root, indexing_policy())
    after = {path.relative_to(root) for path in root.rglob("*") if path.is_file()}
    assert after == before


def test_scanner_source_does_not_execute_repository_files() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "src" / "kronos_engine" / "indexing" / "scanner.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "exec(" not in text
    assert "eval(" not in text
    assert "runpy" not in text
    assert "importlib.import_module" not in text


def test_working_tree_overlay_indexes_uncommitted_and_untracked_files(tmp_path: Path) -> None:
    from kronos_engine.indexing.scanner import list_dirty_paths, scan_with_working_tree

    root = init_git_repo(
        tmp_path / "dirty",
        files={"src/mod.py": "OLD_BLOB_TOKEN = 1\n"},
    )
    (root / "src/mod.py").write_text("NEW_WORKING_TREE_TOKEN = 2\n", encoding="utf-8")
    (root / "src/untracked.py").write_text("UNTRACKED_TOKEN = 3\n", encoding="utf-8")
    blobs = {item.path: item for item in scan_repository(root, indexing_policy())}
    assert "OLD_BLOB_TOKEN" in blobs["src/mod.py"].text
    assert "src/untracked.py" not in blobs

    dirty = set(list_dirty_paths(root))
    assert "src/mod.py" in dirty
    assert "src/untracked.py" in dirty

    overlay = {item.path: item for item in scan_with_working_tree(root, indexing_policy())}
    assert "NEW_WORKING_TREE_TOKEN" in overlay["src/mod.py"].text
    assert "OLD_BLOB_TOKEN" not in overlay["src/mod.py"].text
    assert "UNTRACKED_TOKEN" in overlay["src/untracked.py"].text


def test_working_tree_changes_report_a_status_letter_per_path(tmp_path: Path) -> None:
    from kronos_engine.indexing.scanner import working_tree_changes

    root = init_git_repo(
        tmp_path / "statuses",
        files={"src/mod.py": "OLD = 1\n", "src/gone.py": "GONE = 1\n"},
    )
    (root / "src/mod.py").write_text("NEW = 2\n", encoding="utf-8")
    (root / "src/gone.py").unlink()
    (root / "src/fresh.py").write_text("FRESH = 3\n", encoding="utf-8")

    statuses = {path: status for status, path in working_tree_changes(root)}

    assert statuses["src/mod.py"] == "M"
    assert statuses["src/gone.py"] == "D"
    assert statuses["src/fresh.py"] == "A"


def test_working_tree_overlay_drops_deleted_tracked_files(tmp_path: Path) -> None:
    from kronos_engine.indexing.scanner import scan_with_working_tree

    root = init_git_repo(
        tmp_path / "gone",
        files={
            "src/keep.py": "KEEP_TOKEN = 1\n",
            "src/gone.py": "GONE_TOKEN = 1\n",
        },
    )
    (root / "src/gone.py").unlink()
    overlay = {item.path: item for item in scan_with_working_tree(root, indexing_policy())}
    assert "src/keep.py" in overlay
    assert "src/gone.py" not in overlay


def test_extra_exclude_globs_skip_matching_paths(tmp_path: Path) -> None:
    root = init_git_repo(
        tmp_path / "globs",
        files={
            "src/keep.py": "KEEP_TOKEN = 1\n",
            "src/skip.tmp": "TMP_TOKEN = 1\n",
            "scratch/notes.md": "SCRATCH_TOKEN = 1\n",
        },
    )
    policy = indexing_policy()
    policy = replace(
        policy,
        indexing=replace(policy.indexing, extra_exclude_globs=("*.tmp", "scratch/**")),
    )
    paths = {item.path for item in scan_repository(root, policy)}
    assert "src/keep.py" in paths
    assert "src/skip.tmp" not in paths
    assert "scratch/notes.md" not in paths
