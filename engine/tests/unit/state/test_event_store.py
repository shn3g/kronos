# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest

from kronos_engine.domain.entities import EventId
from kronos_engine.state.database import connect
from kronos_engine.state.event_store import SqliteEventStore


def test_append_assigns_monotonic_seq(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    store = SqliteEventStore(conn)
    first = store.append(EventId("evt-1"), "GoalRecorded", {"goal_id": "g1"})
    second = store.append(EventId("evt-2"), "GoalRecorded", {"goal_id": "g2"})
    assert first.seq == 1
    assert second.seq == 2
    listed = store.list_after(0)
    assert [item.seq for item in listed] == [1, 2]
    assert listed[0].id == EventId("evt-1")


def test_past_events_cannot_be_updated(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    store = SqliteEventStore(conn)
    store.append(EventId("evt-1"), "GoalRecorded", {"goal_id": "g1"})
    with pytest.raises(Exception, match="append-only"):
        conn.execute("UPDATE events SET payload = '{}' WHERE seq = 1")
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM events WHERE seq = 1")
    remaining = store.list_after(0)
    assert len(remaining) == 1
    assert remaining[0].payload == {"goal_id": "g1"}
