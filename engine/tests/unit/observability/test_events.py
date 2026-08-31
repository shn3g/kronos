# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured events cover policy, retrieval, models, git, CI, and writes."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.application.recorder import Recorder
from kronos_engine.observability.events import (
    CI,
    EXTERNAL_WRITE,
    GIT,
    MODEL,
    POLICY,
    RETRIEVAL,
    REVIEW,
    TOOL,
    StructuredEmitter,
)
from kronos_engine.state.database import connect
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.outbox import SqliteOutbox

PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEAfakeprivatekeymaterialforredactiontestxx\n"
    "-----END RSA PRIVATE KEY-----"
)


def _emitter(tmp_path: Path) -> tuple[StructuredEmitter, SqliteEventStore]:
    conn = connect(tmp_path / "kronos.sqlite3")
    events = SqliteEventStore(conn)
    recorder = Recorder(conn, events, SqliteOutbox(conn))
    return StructuredEmitter(recorder), events


def test_structured_emitter_covers_required_kinds_and_redacts_secrets(tmp_path: Path) -> None:
    emitter, store = _emitter(tmp_path)
    kinds = (POLICY, RETRIEVAL, MODEL, TOOL, GIT, CI, REVIEW, EXTERNAL_WRITE)
    for kind in kinds:
        emitter.emit(
            kind,
            {
                "repository_id": "repo_alpha",
                "token": "123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "private_key": PEM,
                "detail": "ok",
            },
        )
    recorded = store.list_after(0)
    assert [item.type for item in recorded] == list(kinds)
    joined = str([dict(item.payload) for item in recorded])
    assert "PRIVATE KEY" not in joined
    assert "123456789:" not in joined
    assert "ok" in joined
    for item in recorded:
        assert item.payload["repository_id"] == "repo_alpha"


def test_span_records_replayable_side_effect_without_secrets(tmp_path: Path) -> None:
    emitter, store = _emitter(tmp_path)
    with emitter.span(
        "external.wrote",
        {"url": "https://api.github.com/repos/acme/app/pulls", "token": "ghs_" + ("B" * 36)},
    ) as span:
        span.set("idempotency_key", "idemp-1")
        span.set("pem", PEM)
    recorded = [item for item in store.list_after(0) if item.type == EXTERNAL_WRITE]
    assert len(recorded) == 1
    payload = dict(recorded[0].payload)
    assert payload["idempotency_key"] == "idemp-1"
    assert payload["url"].endswith("/pulls")
    assert "PRIVATE KEY" not in str(payload)
    assert "ghs_" not in str(payload)
