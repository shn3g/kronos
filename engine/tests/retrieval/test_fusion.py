# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from kronos_engine.indexing.fusion import reciprocal_rank_fusion


def test_reciprocal_rank_fusion_combines_rankings_without_a_query() -> None:
    fused = reciprocal_rank_fusion(
        (
            ("pkg/db.py", "pkg/api.py"),
            ("tests/test_db.py", "pkg/db.py"),
        )
    )
    assert fused[0] in {"pkg/db.py", "tests/test_db.py"}
    assert "pkg/db.py" in fused
    assert "tests/test_db.py" in fused
    signature = inspect.signature(reciprocal_rank_fusion)
    assert "query" not in signature.parameters
    assert signature.parameters["k"].default == 60


def test_score_and_fusion_source_contains_no_query_string_boost_tables() -> None:
    indexing = Path(__file__).resolve().parents[2] / "src" / "kronos_engine" / "indexing"
    blobs: list[str] = []
    trees: list[ast.AST] = []
    for path in indexing.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        blobs.append(text)
        trees.append(ast.parse(text))
    combined = "\n".join(blobs).lower()
    for needle in ("booking", "a11y", "query_boost", "boost_table", "query_weights"):
        assert needle not in combined

    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [key.value for key in node.keys if isinstance(key, ast.Constant)]
                lowered = [str(key).lower() for key in keys if isinstance(key, str)]
                assert "booking" not in lowered
                assert "a11y" not in lowered
                assert not any("boost" in item for item in lowered)
