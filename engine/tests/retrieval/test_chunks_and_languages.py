# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from kronos_engine.indexing.chunks import chunk_text
from kronos_engine.indexing.languages import (
    detect_language,
    extract_imports,
    extract_symbols,
)
from kronos_engine.indexing.scanner import ScannedFile


def test_generic_utf8_chunks_keep_line_ranges() -> None:
    text = "\n".join(f"line-{index}" for index in range(1, 121))
    scanned = ScannedFile(path="notes.txt", text=text + "\n", language="text")
    chunks = chunk_text(scanned, commit="abc123")
    assert chunks
    assert chunks[0].start_line == 1
    assert chunks[0].path == "notes.txt"
    assert chunks[0].commit == "abc123"
    assert chunks[0].content_hash
    assert all(chunk.end_line >= chunk.start_line for chunk in chunks)


def test_python_javascript_and_typescript_symbol_adapters() -> None:
    py = extract_symbols(
        "class Store:\n    pass\n\ndef connect(dsn: str) -> str:\n    return dsn\n",
        "python",
    )
    names = {item.name for item in py}
    assert "Store" in names
    assert "connect" in names
    assert {item.kind for item in py} <= {"class", "function"}

    js = extract_symbols("function renderShell() {\n  return 'ok';\n}\n", "javascript")
    assert any(item.name == "renderShell" for item in js)

    ts = extract_symbols(
        "export function fetchSession(id: string): Promise<string> {\n"
        "  return Promise.resolve(id);\n"
        "}\n",
        "typescript",
    )
    assert any(item.name == "fetchSession" for item in ts)

    imports = extract_imports("from pkg.db import connect\n", "python")
    assert any("pkg.db" in item for item in imports)


def test_detect_language_from_path() -> None:
    assert detect_language("pkg/db.py") == "python"
    assert detect_language("web/app.js") == "javascript"
    assert detect_language("web/client.ts") == "typescript"
    assert detect_language("docs/overview.md") == "markdown"


def test_tree_sitter_python_js_ts_symbol_names_and_line_ranges() -> None:
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_python")
    pytest.importorskip("tree_sitter_javascript")
    pytest.importorskip("tree_sitter_typescript")
    from kronos_engine.indexing.languages import _tree_sitter_symbols

    py_src = "class Store:\n    pass\n\ndef connect(dsn: str) -> str:\n    return dsn\n"
    py = _tree_sitter_symbols(py_src, "python")
    assert py is not None
    by_name = {item.name: item for item in py}
    assert by_name["Store"].kind == "class"
    assert by_name["Store"].start_line == 1
    assert by_name["Store"].end_line >= 2
    assert by_name["connect"].kind == "function"
    assert by_name["connect"].start_line == 4
    assert by_name["connect"].end_line >= 4

    js_src = "function renderShell() {\n  return 'ok';\n}\n"
    js = _tree_sitter_symbols(js_src, "javascript")
    assert js is not None
    assert any(item.name == "renderShell" and item.start_line == 1 for item in js)

    ts_src = (
        "export function fetchSession(id: string): Promise<string> {\n"
        "  return Promise.resolve(id);\n"
        "}\n"
    )
    ts = _tree_sitter_symbols(ts_src, "typescript")
    assert ts is not None
    assert any(item.name == "fetchSession" and item.start_line == 1 for item in ts)
