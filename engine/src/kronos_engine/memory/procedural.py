# SPDX-License-Identifier: AGPL-3.0-or-later
"""Procedural lesson and skill candidates. Propose is not activate."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import struct
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from kronos_engine.memory.records import (
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    clamp_confidence,
    validate_memory_text,
)
from kronos_engine.ports.embedding import EmbeddingPort

_WORD = re.compile(r"[A-Za-z0-9]+")


class ProceduralStore:
    def __init__(
        self,
        conn: sqlite3.Connection,
        embeddings: EmbeddingPort | None = None,
    ) -> None:
        self._conn = conn
        self._embeddings = embeddings

    def propose(
        self,
        *,
        text: str,
        source_sha: str,
        confidence: float,
        skill_id: str | None = None,
        provenance: dict[str, object] | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            id=f"mem-proc-{uuid4().hex[:12]}",
            kind=MemoryKind.procedural.value,
            text=validate_memory_text(text),
            source_sha=source_sha,
            outcome="neutral",
            confidence=clamp_confidence(confidence),
            helpful=0,
            harmful=0,
            status=MemoryStatus.proposed,
            independent_sources=(source_sha,) if source_sha else (),
            skill_id=skill_id,
            created_at=datetime.now(tz=UTC).isoformat(),
            provenance=dict(provenance or {}),
        )
        persist_record(self._conn, record, self._embeddings)
        return record

    def import_lessons(self, text: str) -> tuple[MemoryRecord, ...]:
        imported: list[MemoryRecord] = []
        for item in parse_lessons_yaml(text):
            ident = str(item.get("id") or f"lesson-{uuid4().hex[:8]}")
            body = validate_memory_text(str(item.get("text") or ""))
            source_pr = str(item.get("source_pr") or "")
            source_sha = hashlib.sha1(f"{ident}:{source_pr}".encode()).hexdigest()
            helpful = _as_int(item.get("helpful"))
            harmful = _as_int(item.get("harmful"))
            record = MemoryRecord(
                id=ident,
                kind=MemoryKind.procedural.value,
                text=body,
                source_sha=source_sha,
                outcome="neutral",
                confidence=0.0,
                helpful=helpful,
                harmful=harmful,
                status=MemoryStatus.disabled_candidate,
                independent_sources=(),
                skill_id=None,
                created_at=str(item.get("created") or datetime.now(tz=UTC).isoformat()),
                provenance={"source_pr": source_pr, "import": "yaml"},
            )
            persist_record(self._conn, record, self._embeddings)
            imported.append(record)
        return tuple(imported)

    def for_skill(self, skill_id: str) -> MemoryRecord:
        record = _latest_for_skill(self._conn, skill_id)
        if record is None:
            raise LookupError(skill_id)
        return record

    def get(self, record_id: str) -> MemoryRecord | None:
        return load_record(self._conn, record_id)

    def list(self) -> tuple[MemoryRecord, ...]:
        return load_records(self._conn)

    def save(self, record: MemoryRecord) -> MemoryRecord:
        persist_record(self._conn, record, self._embeddings)
        return record


def parse_lessons_yaml(text: str) -> tuple[dict[str, object], ...]:
    items: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped in {"lessons:", "lessons: []"}:
            continue
        if stripped.startswith("- "):
            if current:
                items.append(current)
            current = {}
            rest = stripped[2:]
            _assign(current, rest)
            continue
        if current is not None:
            _assign(current, stripped)
    if current:
        items.append(current)
    return tuple(items)


def persist_record(
    conn: sqlite3.Connection,
    record: MemoryRecord,
    embeddings: EmbeddingPort | None,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_records(
            id, kind, text, source_sha, outcome, confidence, helpful, harmful,
            status, skill_id, independent_sources_json, provenance_json, created_at,
            run_id, task_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            text = excluded.text,
            source_sha = excluded.source_sha,
            outcome = excluded.outcome,
            confidence = excluded.confidence,
            helpful = excluded.helpful,
            harmful = excluded.harmful,
            status = excluded.status,
            skill_id = excluded.skill_id,
            independent_sources_json = excluded.independent_sources_json,
            provenance_json = excluded.provenance_json,
            run_id = excluded.run_id,
            task_id = excluded.task_id
        """,
        (
            record.id,
            record.kind,
            record.text,
            record.source_sha,
            record.outcome,
            record.confidence,
            record.helpful,
            record.harmful,
            record.status.value,
            record.skill_id,
            json.dumps(list(record.independent_sources)),
            json.dumps(record.provenance),
            record.created_at,
            record.run_id,
            record.task_id,
        ),
    )
    conn.execute("DELETE FROM memory_fts WHERE record_id = ?", (record.id,))
    conn.execute(
        "INSERT INTO memory_fts(record_id, text) VALUES (?, ?)",
        (record.id, record.text),
    )
    conn.execute("DELETE FROM memory_vectors WHERE record_id = ?", (record.id,))
    if embeddings is not None and embeddings.available("document"):
        vectors = embeddings.embed([record.text], kind="document")
        if vectors is not None and len(vectors) == 1:
            vector = [float(value) for value in vectors[0]]
            payload = struct.pack(f"{len(vector)}f", *vector)
            conn.execute(
                "INSERT INTO memory_vectors(record_id, kind, dim, embedding) VALUES (?, ?, ?, ?)",
                (record.id, "document", len(vector), payload),
            )
    conn.commit()


def backfill_memory_vectors(
    conn: sqlite3.Connection,
    embeddings: EmbeddingPort | None,
) -> int:
    if embeddings is None or not embeddings.available("document"):
        return 0
    rows = conn.execute(
        """
        SELECT r.id, r.text
        FROM memory_records r
        WHERE NOT EXISTS (
            SELECT 1 FROM memory_vectors v WHERE v.record_id = r.id
        )
        ORDER BY r.created_at, r.id
        """
    ).fetchall()
    if not rows:
        return 0
    vectors = embeddings.embed([str(row["text"]) for row in rows], kind="document")
    if vectors is None or len(vectors) != len(rows):
        return 0
    filled = 0
    for row, vector in zip(rows, vectors, strict=True):
        values = [float(value) for value in vector]
        payload = struct.pack(f"{len(values)}f", *values)
        conn.execute(
            "INSERT INTO memory_vectors(record_id, kind, dim, embedding) VALUES (?, ?, ?, ?)",
            (str(row["id"]), "document", len(values), payload),
        )
        filled += 1
    conn.commit()
    return filled


def load_record(conn: sqlite3.Connection, record_id: str) -> MemoryRecord | None:
    row = conn.execute("SELECT * FROM memory_records WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        return None
    return _from_row(row)


def load_records(conn: sqlite3.Connection, kind: str | None = None) -> tuple[MemoryRecord, ...]:
    if kind is None:
        rows = conn.execute("SELECT * FROM memory_records ORDER BY created_at").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memory_records WHERE kind = ? ORDER BY created_at", (kind,)
        ).fetchall()
    return tuple(_from_row(row) for row in rows)


def retrieve_records(
    conn: sqlite3.Connection,
    query: str,
    embeddings: EmbeddingPort | None,
    *,
    limit: int = 5,
) -> tuple[MemoryRecord, ...]:
    from kronos_engine.indexing.fusion import reciprocal_rank_fusion

    tokens = [token.lower() for token in _WORD.findall(query)]
    sparse: list[str] = []
    if tokens:
        match = " OR ".join(tokens)
        rows = conn.execute(
            "SELECT record_id FROM memory_fts WHERE memory_fts MATCH ?",
            (match,),
        ).fetchall()
        sparse = [str(row["record_id"]) for row in rows]
    dense: list[str] = []
    if embeddings is not None and embeddings.available("document"):
        vectors = embeddings.embed([query], kind="document")
        if vectors:
            dense = list(_search_dense(conn, [float(value) for value in vectors[0]]))
    if not sparse and not dense:
        return ()
    fused = reciprocal_rank_fusion(tuple(item for item in (sparse, dense) if item))
    records = []
    for record_id in fused[: limit * 4]:
        loaded = load_record(conn, record_id)
        if loaded is not None and loaded.status is MemoryStatus.active:
            records.append(loaded)
        if len(records) >= limit:
            break
    return tuple(records)


def _search_dense(conn: sqlite3.Connection, query: Sequence[float]) -> tuple[str, ...]:
    rows = conn.execute("SELECT record_id, dim, embedding FROM memory_vectors").fetchall()
    scored: list[tuple[float, str]] = []
    for row in rows:
        stored = list(struct.unpack(f"{int(row['dim'])}f", row["embedding"]))
        scored.append((_cosine(query, stored), str(row["record_id"])))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(record_id for score, record_id in scored if score > 0.0)


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


def _latest_for_skill(conn: sqlite3.Connection, skill_id: str) -> MemoryRecord | None:
    row = conn.execute(
        """
        SELECT * FROM memory_records
        WHERE skill_id = ? AND kind = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (skill_id, MemoryKind.procedural.value),
    ).fetchone()
    if row is None:
        return None
    return _from_row(row)


def _from_row(row: sqlite3.Row) -> MemoryRecord:
    sources = json.loads(row["independent_sources_json"] or "[]")
    provenance = json.loads(row["provenance_json"] or "{}")
    return MemoryRecord(
        id=row["id"],
        kind=row["kind"],
        text=row["text"],
        source_sha=row["source_sha"],
        outcome=row["outcome"],
        confidence=float(row["confidence"]),
        helpful=int(row["helpful"]),
        harmful=int(row["harmful"]),
        status=MemoryStatus(row["status"]),
        independent_sources=tuple(str(item) for item in sources),
        skill_id=row["skill_id"],
        created_at=row["created_at"],
        provenance=dict(provenance),
        run_id=row["run_id"],
        task_id=row["task_id"],
    )


def _assign(current: dict[str, object], raw: str) -> None:
    key, sep, rest = raw.partition(":")
    if sep == "":
        return
    current[key.strip()] = _scalar(rest.strip())


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and (
        value.isdigit() or (value.startswith("-") and value[1:].isdigit())
    ):
        return int(value)
    return 0


def _scalar(raw: str) -> object:
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return int(raw)
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    return raw
