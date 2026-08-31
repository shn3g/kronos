# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-repository index storage. One store instance must not read another repo."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    symbol: str | None
    kind: str
    language: str
    commit: str
    content_hash: str
    text: str
    trust: str


@dataclass(frozen=True, slots=True)
class Relation:
    src_path: str
    dst_path: str
    rel_type: str


class IndexStore(Protocol):
    def replace_all(
        self, chunks: Sequence[IndexedChunk], relations: Sequence[Relation]
    ) -> None: ...

    def delete_paths(self, paths: Sequence[str]) -> None: ...

    def upsert(self, chunks: Sequence[IndexedChunk]) -> None: ...

    def replace_relations(self, relations: Sequence[Relation]) -> None: ...

    def list_chunks(self) -> Sequence[IndexedChunk]: ...

    def chunks_for_path(self, path: str) -> Sequence[IndexedChunk]: ...

    def get_chunk(self, chunk_id: str) -> IndexedChunk | None: ...

    def search_sparse(self, query: str, limit: int) -> Sequence[str]: ...

    def indexed_commit(self) -> str | None: ...

    def set_indexed_commit(self, commit: str) -> None: ...
