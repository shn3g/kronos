# SPDX-License-Identifier: AGPL-3.0-or-later
"""Disposable dense vectors. MiniLM document kind never indexes source code."""

from __future__ import annotations

import math
import sqlite3
import struct
from collections.abc import Sequence

from kronos_engine.ports.embedding import EmbeddingPort
from kronos_engine.ports.index_store import IndexedChunk

DOCUMENT_LANGUAGES = frozenset({"markdown", "text"})


def embedding_kind_for(language: str) -> str:
    if language in DOCUMENT_LANGUAGES:
        return "document"
    return "code"


def upsert_embeddings(
    conn: sqlite3.Connection,
    chunks: Sequence[IndexedChunk],
    embeddings: EmbeddingPort,
) -> bool:
    used = False
    by_kind: dict[str, list[IndexedChunk]] = {}
    for chunk in chunks:
        kind = embedding_kind_for(chunk.language)
        by_kind.setdefault(kind, []).append(chunk)
    for kind, group in by_kind.items():
        if kind == "document" and any(item.language not in DOCUMENT_LANGUAGES for item in group):
            continue
        if not embeddings.available(kind):
            continue
        vectors = embeddings.embed([item.text for item in group], kind=kind)
        if vectors is None or len(vectors) != len(group):
            continue
        used = True
        for chunk, vector in zip(group, vectors, strict=True):
            payload = struct.pack(f"{len(vector)}f", *[float(value) for value in vector])
            conn.execute(
                """
                INSERT OR REPLACE INTO vectors (chunk_id, kind, dim, embedding)
                VALUES (?, ?, ?, ?)
                """,
                (chunk.chunk_id, kind, len(vector), payload),
            )
    conn.commit()
    return used


def search_dense(
    conn: sqlite3.Connection,
    vector: Sequence[float],
    *,
    kind: str,
    limit: int,
) -> tuple[str, ...]:
    rows = conn.execute(
        "SELECT chunk_id, dim, embedding FROM vectors WHERE kind = ?", (kind,)
    ).fetchall()
    scored: list[tuple[float, str]] = []
    query = [float(value) for value in vector]
    for row in rows:
        stored = _unpack(row["embedding"], int(row["dim"]))
        scored.append((_cosine(query, stored), row["chunk_id"]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(chunk_id for _score, chunk_id in scored[:limit])


def drop_vectors(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM vectors")
    conn.commit()


def _unpack(blob: bytes, dim: int) -> list[float]:
    return list(struct.unpack(f"{dim}f", blob))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
