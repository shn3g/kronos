# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from kronos_engine.indexing.chunks import chunk_text
from kronos_engine.indexing.languages import detect_language, extract_imports, extract_symbols
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


def test_languages_module_declares_tree_sitter_adapters() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "kronos_engine"
        / "indexing"
        / "languages.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "tree-sitter" in text.lower() or "tree_sitter" in text
    assert "python" in text
    assert "javascript" in text
    assert "typescript" in text
