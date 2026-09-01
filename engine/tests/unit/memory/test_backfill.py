# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backfill memory_vectors for rows stored before an embedder was available."""

from __future__ import annotations

import struct
from pathlib import Path

from kronos_engine.memory.procedural import backfill_memory_vectors, persist_record
from kronos_engine.memory.records import MemoryKind, MemoryRecord, MemoryStatus
from kronos_engine.state.database import Database


class _FakeEmbedder:
    def __init__(self, *, available: bool = True) -> None:
        self.available_flag = available
        self.seen: list[str] = []

    def available(self, kind: str) -> bool:
        return self.available_flag and kind == "document"

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]] | None:
        _ = kind
        self.seen.extend(texts)
        return [[float(len(text)), 1.0, 0.5] for text in texts]


def _record(ident: str, text: str) -> MemoryRecord:
    return MemoryRecord(
        id=ident,
        kind=MemoryKind.procedural.value,
        text=text,
        source_sha=f"sha-{ident}",
        outcome="neutral",
        confidence=0.4,
        helpful=0,
        harmful=0,
        status=MemoryStatus.proposed,
        independent_sources=(),
        skill_id=None,
        created_at="2026-01-01T00:00:00+00:00",
        provenance={},
    )


def test_backfill_embeds_records_missing_vectors(tmp_path: Path) -> None:
    conn = Database(tmp_path / "kronos.sqlite3").connect()
    persist_record(conn, _record("mem-a", "first lesson"), embeddings=None)
    persist_record(conn, _record("mem-b", "second lesson"), embeddings=None)
    assert conn.execute("SELECT COUNT(*) AS n FROM memory_vectors").fetchone()["n"] == 0

    embedder = _FakeEmbedder()
    filled = backfill_memory_vectors(conn, embedder)
    assert filled == 2
    assert embedder.seen == ["first lesson", "second lesson"]
    rows = {
        str(row["record_id"]): row
        for row in conn.execute("SELECT record_id, dim, embedding FROM memory_vectors")
    }
    assert set(rows) == {"mem-a", "mem-b"}
    unpacked = list(struct.unpack(f"{int(rows['mem-a']['dim'])}f", rows["mem-a"]["embedding"]))
    assert unpacked == [float(len("first lesson")), 1.0, 0.5]


def test_backfill_is_noop_without_embedder_and_skips_existing_vectors(tmp_path: Path) -> None:
    conn = Database(tmp_path / "kronos.sqlite3").connect()
    live = _FakeEmbedder()
    persist_record(conn, _record("mem-existing", "already embedded"), embeddings=live)
    persist_record(conn, _record("mem-missing", "needs a vector"), embeddings=None)
    assert conn.execute("SELECT COUNT(*) AS n FROM memory_vectors").fetchone()["n"] == 1

    assert backfill_memory_vectors(conn, None) == 0
    assert backfill_memory_vectors(conn, _FakeEmbedder(available=False)) == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM memory_vectors").fetchone()["n"] == 1

    filled = backfill_memory_vectors(conn, _FakeEmbedder())
    assert filled == 1
    ids = {
        str(row["record_id"])
        for row in conn.execute("SELECT record_id FROM memory_vectors")
    }
    assert ids == {"mem-existing", "mem-missing"}
