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
