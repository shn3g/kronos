# SPDX-License-Identifier: AGPL-3.0-or-later
"""Definition, reference, import, and test relationships."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kronos_engine.indexing.languages import extract_imports, extract_symbols
from kronos_engine.ports.index_store import IndexedChunk, Relation


def build_relations(chunks: Sequence[IndexedChunk]) -> tuple[Relation, ...]:
    by_path: dict[str, list[IndexedChunk]] = {}
    for chunk in chunks:
        by_path.setdefault(chunk.path, []).append(chunk)
    paths = tuple(sorted(by_path))
    relations: list[Relation] = []
    stems: dict[str, list[str]] = {}
    for path in paths:
        stems.setdefault(Path(path).stem, []).append(path)
        file_text = "\n".join(item.text for item in by_path[path])
        language = by_path[path][0].language
        for imported in extract_imports(file_text, language):
            target = _resolve_import(imported, paths)
            if target is not None and target != path:
                relations.append(Relation(src_path=path, dst_path=target, rel_type="imports"))
        for symbol in extract_symbols(file_text, language):
            relations.append(
                Relation(src_path=path, dst_path=path, rel_type=f"defines:{symbol.name}")
            )
            for other in paths:
                if other == path:
                    continue
                other_text = "\n".join(item.text for item in by_path[other])
                if _contains_word(other_text, symbol.name):
                    relations.append(
                        Relation(src_path=other, dst_path=path, rel_type="references")
                    )
    for path in paths:
        target_stem = _test_target_stem(path)
        if target_stem is None:
            continue
        for candidate in stems.get(target_stem, ()):
            if candidate == path or _is_test_path(candidate):
                continue
            relations.append(Relation(src_path=path, dst_path=candidate, rel_type="tests"))
    return tuple(dict.fromkeys(relations))


def expand_paths(
    seed_paths: Sequence[str], relations: Sequence[Relation], *, limit: int
) -> tuple[str, ...]:
    seeds = {path.replace("\\", "/") for path in seed_paths}
    extra: list[str] = []
    for relation in relations:
        if relation.src_path in seeds and relation.dst_path not in seeds:
            extra.append(relation.dst_path)
        if (
            relation.rel_type == "tests"
            and relation.dst_path in seeds
            and relation.src_path not in seeds
        ):
            extra.append(relation.src_path)
    ordered = list(dict.fromkeys(extra))
    return tuple(ordered[:limit])


def _test_target_stem(path: str) -> str | None:
    posix = path.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    if not _is_test_path(posix):
        return None
    if name.startswith("test_") and name.endswith(".py"):
        return name[len("test_") : -len(".py")]
    return None


def _is_test_path(path: str) -> bool:
    posix = path.replace("\\", "/")
    return "/tests/" in f"/{posix}/" or posix.startswith("tests/")


def _resolve_import(module: str, paths: Sequence[str]) -> str | None:
    dotted = module.replace(".", "/")
    candidates = (f"{dotted}.py", f"{dotted}/__init__.py")
    for path in paths:
        if path in candidates or path.endswith("/" + candidates[0]):
            return path
    return None


def _contains_word(text: str, word: str) -> bool:
    if word == "" or word not in text:
        return False
    index = 0
    while True:
        found = text.find(word, index)
        if found < 0:
            return False
        before = text[found - 1] if found > 0 else ""
        after = text[found + len(word)] if found + len(word) < len(text) else ""
        if (not before.isalnum() and before != "_") and (not after.isalnum() and after != "_"):
            return True
        index = found + len(word)
