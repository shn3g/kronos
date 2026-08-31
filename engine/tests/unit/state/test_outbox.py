# SPDX-License-Identifier: AGPL-3.0-or-later

import sqlite3
from pathlib import Path

import pytest

from kronos_engine.application.recorder import Recorder
from kronos_engine.domain.entities import EventId
from kronos_engine.domain.results import AlreadyDispatchedError
from kronos_engine.state.database import connect
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.outbox import SqliteOutbox


def make_recorder(conn: sqlite3.Connection) -> Recorder:
    return Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn))


def test_outbox_row_is_inserted_in_the_same_transaction_as_the_event(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    recorder = make_recorder(conn)
    stored, row = recorder.record(
        EventId("evt-1"),
        "GoalRecorded",
        {"goal_id": "g1"},
        {"action": "notify", "goal_id": "g1"},
    )
    assert stored.seq == row.event_seq
    assert SqliteOutbox(conn).undispatched() == (row,)


def test_rollback_writes_neither_event_nor_outbox(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    events = SqliteEventStore(conn)
    outbox = SqliteOutbox(conn)
    conn.execute("BEGIN")
    events.append(EventId("evt-1"), "GoalRecorded", {"goal_id": "g1"})
    outbox.enqueue(1, {"action": "notify"})
    conn.rollback()
    assert events.list_after(0) == ()
    assert outbox.undispatched() == ()


def test_restart_does_not_duplicate_undispatched_rows(tmp_path: Path) -> None:
    db = tmp_path / "kronos.sqlite3"
    conn = connect(db)
    make_recorder(conn).record(
        EventId("evt-1"),
        "GoalRecorded",
        {"goal_id": "g1"},
        {"action": "notify"},
    )
    conn.close()

    restarted = connect(db)
    try:
        rows = SqliteOutbox(restarted).undispatched()
        assert len(rows) == 1
        assert rows[0].payload == {"action": "notify"}
        with pytest.raises(Exception):
            make_recorder(restarted).record(
                EventId("evt-1"),
                "GoalRecorded",
                {"goal_id": "g1"},
                {"action": "notify"},
            )
        assert len(SqliteOutbox(restarted).undispatched()) == 1
    finally:
        restarted.close()


def test_mark_dispatched_exactly_once(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    _, row = make_recorder(conn).record(
        EventId("evt-1"),
        "GoalRecorded",
        {"goal_id": "g1"},
        {"action": "notify"},
    )
    outbox = SqliteOutbox(conn)
    outbox.mark_dispatched(row.id)
    assert outbox.undispatched() == ()
    with pytest.raises(AlreadyDispatchedError):
        outbox.mark_dispatched(row.id)
    assert outbox.undispatched() == ()
