# SPDX-License-Identifier: AGPL-3.0-or-later
"""Token-budgeted context packing and repository maps."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from kronos_engine.ports.index_store import IndexedChunk


@dataclass(frozen=True, slots=True)
class ContextItem:
    path: str
    start_line: int
    end_line: int
    commit: str
    text: str
    symbol: str | None
    rank_sources: tuple[str, ...]
    trust: str


@dataclass(frozen=True, slots=True)
class ContextPack:
    items: tuple[ContextItem, ...]


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def assemble_context(
    chunks: Sequence[tuple[IndexedChunk, tuple[str, ...]]],
    *,
    budget_tokens: int,
) -> ContextPack:
    packed: list[ContextItem] = []
    used = 0
    seen_paths: set[str] = set()
    for chunk, sources in chunks:
        cost = estimate_tokens(chunk.text)
        if packed and used + cost > budget_tokens:
            break
        packed.append(
            ContextItem(
                path=chunk.path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                commit=chunk.commit,
                text=chunk.text,
                symbol=chunk.symbol,
                rank_sources=sources,
                trust=chunk.trust,
            )
        )
        seen_paths.add(chunk.path)
        used += cost
    _ = seen_paths
    return ContextPack(items=tuple(packed))


def repo_map(chunks: Sequence[IndexedChunk], *, budget_tokens: int) -> str:
    symbols: dict[str, list[str]] = {}
    for chunk in chunks:
        names = symbols.setdefault(chunk.path, [])
        if chunk.symbol and chunk.symbol not in names:
            names.append(chunk.symbol)
    lines: list[str] = []
    used = 0
    for path in sorted(symbols):
        names = symbols[path]
        suffix = ", ".join(names) if names else ""
        line = f"{path}: {suffix}".rstrip()
        cost = estimate_tokens(line)
        if lines and used + cost > budget_tokens:
            break
        lines.append(line)
        used += cost
    return "\n".join(lines)
