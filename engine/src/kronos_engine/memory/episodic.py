# SPDX-License-Identifier: AGPL-3.0-or-later
"""Episodic run and outcome records. Text is the source of truth."""

from __future__ import annotations

import sqlite3
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


class EpisodicStore:
    def __init__(
        self,
        conn: sqlite3.Connection,
        embeddings: EmbeddingPort | None = None,
    ) -> None:
        self._conn = conn
        self._embeddings = embeddings

    def record(
        self,
        *,
        text: str,
        source_sha: str,
        outcome: str,
        confidence: float,
        run_id: str | None = None,
        task_id: str | None = None,
        skill_id: str | None = None,
        provenance: dict[str, object] | None = None,
    ) -> MemoryRecord:
        from kronos_engine.memory.procedural import persist_record

        record = MemoryRecord(
            id=f"mem-episodic-{uuid4().hex[:12]}",
            kind=MemoryKind.episodic.value,
            text=validate_memory_text(text),
            source_sha=source_sha,
            outcome=outcome,
            confidence=clamp_confidence(confidence),
            helpful=1 if outcome == "helpful" else 0,
            harmful=1 if outcome == "harmful" else 0,
            status=MemoryStatus.proposed,
            independent_sources=(source_sha,),
            skill_id=skill_id,
            created_at=datetime.now(tz=UTC).isoformat(),
            provenance=dict(provenance or {}),
            run_id=run_id,
            task_id=task_id,
        )
        persist_record(self._conn, record, self._embeddings)
        return record

    def list(self) -> tuple[MemoryRecord, ...]:
        from kronos_engine.memory.procedural import load_records

        return load_records(self._conn, kind=MemoryKind.episodic.value)

    def get(self, record_id: str) -> MemoryRecord | None:
        from kronos_engine.memory.procedural import load_record

        return load_record(self._conn, record_id)
