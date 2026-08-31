# SPDX-License-Identifier: AGPL-3.0-or-later
"""Language detection and tree-sitter Python/JavaScript/TypeScript symbol adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PY_DEF = re.compile(r"^([ \t]*)(?:async\s+)?def\s+(\w+)", re.MULTILINE)
_PY_CLASS = re.compile(r"^([ \t]*)class\s+(\w+)", re.MULTILINE)
_PY_IMPORT = re.compile(
    r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)
_JS_FN = re.compile(
    r"^([ \t]*)(?:export\s+)?(?:async\s+)?function\s+(\w+)",
    re.MULTILINE,
)
_JS_CLASS = re.compile(r"^([ \t]*)(?:export\s+)?class\s+(\w+)", re.MULTILINE)
_JS_IMPORT = re.compile(r"""from\s+['"]([^'"]+)['"]""")

_SUFFIX_LANGUAGE = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".md": "markdown",
    ".rst": "markdown",
    ".txt": "text",
}


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    kind: str
    start_line: int
    end_line: int


def detect_language(path: str) -> str:
    posix = path.replace("\\", "/")
    dot = posix.rfind(".")
    if dot < 0:
        return "text"
    return _SUFFIX_LANGUAGE.get(posix[dot:].lower(), "text")


def extract_symbols(text: str, language: str) -> tuple[Symbol, ...]:
    parsed = _tree_sitter_symbols(text, language)
    if parsed is not None:
        return parsed
    return _regex_symbols(text, language)


def extract_imports(text: str, language: str) -> tuple[str, ...]:
    if language == "python":
        found: list[str] = []
        for match in _PY_IMPORT.finditer(text):
            module = match.group(1) or match.group(2) or ""
            if module:
                found.append(module)
        return tuple(found)
    if language in {"javascript", "typescript"}:
        return tuple(_JS_IMPORT.findall(text))
    return ()


def _regex_symbols(text: str, language: str) -> tuple[Symbol, ...]:
    if language == "python":
        events = _line_events(text, ((_PY_CLASS, "class"), (_PY_DEF, "function")))
        return _ranges_from_events(text, events)
    if language in {"javascript", "typescript"}:
        events = _line_events(text, ((_JS_CLASS, "class"), (_JS_FN, "function")))
        return _ranges_from_events(text, events)
    return ()


def _line_events(
    text: str, patterns: tuple[tuple[re.Pattern[str], str], ...]
) -> list[tuple[int, int, str, str]]:
    events: list[tuple[int, int, str, str]] = []
    for pattern, kind in patterns:
        for match in pattern.finditer(text):
            indent = len(match.group(1).replace("\t", "    "))
            name = match.group(2)
            line = text.count("\n", 0, match.start()) + 1
            events.append((line, indent, kind, name))
    events.sort(key=lambda item: item[0])
    return events


def _ranges_from_events(
    text: str, events: list[tuple[int, int, str, str]]
) -> tuple[Symbol, ...]:
    total = text.count("\n") + (0 if text.endswith("\n") or text == "" else 1)
    if text == "":
        total = 0
    symbols: list[Symbol] = []
    for index, (line, indent, kind, name) in enumerate(events):
        end = total
        for later_line, later_indent, _kind, _name in events[index + 1 :]:
            if later_indent <= indent:
                end = later_line - 1
                break
        symbols.append(Symbol(name=name, kind=kind, start_line=line, end_line=max(line, end)))
    return tuple(symbols)


def _tree_sitter_symbols(text: str, language: str) -> tuple[Symbol, ...] | None:
    """Prefer tree-sitter grammars when the optional language packages are installed."""
    try:
        from tree_sitter import (
            Language,
            Parser,
            Query,
            QueryCursor,
        )
    except ImportError:
        return None
    language_id = None
    query_src = ""
    try:
        if language == "python":
            import tree_sitter_python as ts_python

            language_id = Language(ts_python.language())
            query_src = """
            (function_definition name: (identifier) @name)
            (class_definition name: (identifier) @name)
            """
        elif language == "javascript":
            import tree_sitter_javascript as ts_javascript

            language_id = Language(ts_javascript.language())
            query_src = """
            (function_declaration name: (identifier) @name)
            (class_declaration name: (identifier) @name)
            """
        elif language == "typescript":
            import tree_sitter_typescript as ts_typescript

            language_id = Language(ts_typescript.language_typescript())
            query_src = """
            (function_declaration (identifier) @name)
            (class_declaration (type_identifier) @name)
            """
        else:
            return None
    except ImportError:
        return None
    if language_id is None:
        return None
    parser = Parser(language_id)
    tree = parser.parse(text.encode("utf-8"))
    query = Query(language_id, query_src)
    captures = QueryCursor(query).captures(tree.root_node)
    found: list[Symbol] = []
    nodes = captures.get("name", []) if isinstance(captures, dict) else []
    if not nodes and isinstance(captures, list):
        nodes = [node for node, name in captures if name == "name"]
    for node in nodes:
        parent_type = node.parent.type if node.parent is not None else ""
        kind = "class" if "class" in parent_type else "function"
        start = node.start_point[0] + 1
        end = (node.parent.end_point[0] + 1) if node.parent is not None else start
        raw = node.text
        if raw is None:
            continue
        found.append(
            Symbol(name=raw.decode("utf-8"), kind=kind, start_line=start, end_line=end)
        )
    return tuple(found) if found else None
