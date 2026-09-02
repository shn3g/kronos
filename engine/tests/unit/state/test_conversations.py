# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kronos_engine.state.conversations import SqliteConversationStore
from kronos_engine.state.database import connect


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "kronos.sqlite3")
    connection.execute(
        "INSERT INTO repositories("
        "id, realpath, origin, display_name, status, policy_json, enrolled_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("repo_1", str(tmp_path), None, "repo", "active", "{}", "2026-01-01T00:00:00Z"),
    )
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def test_create_and_list_conversations_for_a_repository(conn: sqlite3.Connection) -> None:
    store = SqliteConversationStore(conn)
    record = store.create("repo_1", "Scoped")
    assert record.repository_id == "repo_1"
    listed = store.list_for_repository("repo_1")
    assert [item.id for item in listed] == [record.id]


def test_create_accepts_a_null_repository(conn: sqlite3.Connection) -> None:
    store = SqliteConversationStore(conn)
    record = store.create(None, "No workspace")
    assert record.repository_id is None
    assert store.get(record.id).repository_id is None
    assert [item.id for item in store.list_for_repository(None)] == [record.id]
    assert store.list_for_repository("repo_1") == ()


def test_list_for_repository_excludes_null_rows(conn: sqlite3.Connection) -> None:
    store = SqliteConversationStore(conn)
    scoped = store.create("repo_1", "Scoped")
    store.create(None, "Loose")
    assert [item.id for item in store.list_for_repository("repo_1")] == [scoped.id]


def test_add_message_persists_tool_rows(conn: sqlite3.Connection) -> None:
    store = SqliteConversationStore(conn)
    conversation = store.create("repo_1", "Tools")
    store.add_message(conversation.id, role="user", content="read the readme")
    tool = store.add_message(
        conversation.id,
        role="tool",
        content="read_file README.md",
        tool_name="read_file",
        tool_status="ok",
        tool_json='{"path": "README.md"}',
    )
    assert tool.tool_name == "read_file"
    assert tool.tool_status == "ok"
    assert tool.tool_json == '{"path": "README.md"}'
    messages = store.list_messages(conversation.id)
    assert [item.role for item in messages] == ["user", "tool"]
    assert messages[0].tool_name is None
    assert messages[0].tool_status is None
    assert messages[0].tool_json is None
    assert messages[1].tool_json == '{"path": "README.md"}'


def test_file_backups_round_trip(conn: sqlite3.Connection) -> None:
    store = SqliteConversationStore(conn)
    assert store.get_file_backup("repo_1", "src/a.py") is None
    assert store.list_backup_paths("repo_1") == ()

    store.save_file_backup("repo_1", "src/a.py", "one", "2026-01-01T00:00:00Z")
    store.save_file_backup("repo_1", "src/b.py", "two", "2026-01-01T00:00:01Z")
    assert store.get_file_backup("repo_1", "src/a.py") == "one"
    assert store.list_backup_paths("repo_1") == ("src/a.py", "src/b.py")

    store.save_file_backup("repo_1", "src/a.py", "one-updated", "2026-01-01T00:00:02Z")
    assert store.get_file_backup("repo_1", "src/a.py") == "one-updated"
    assert store.list_backup_paths("repo_1") == ("src/a.py", "src/b.py")

    store.delete_file_backup("repo_1", "src/a.py")
    assert store.get_file_backup("repo_1", "src/a.py") is None
    assert store.list_backup_paths("repo_1") == ("src/b.py",)
    assert store.list_backup_paths("repo_2") == ()
