# SPDX-License-Identifier: AGPL-3.0-or-later

import sqlite3
from pathlib import Path

from kronos_engine.state.database import connect
from kronos_engine.state.migrations import MIGRATIONS, apply_migrations


def _open_at_version(path: Path, version: int) -> sqlite3.Connection:
    """Open a database migrated only up to ``version``, bypassing connect()."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for number, sql in MIGRATIONS:
        if number > version:
            break
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2026-01-01T00:00:00Z')",
            (number,),
        )
    conn.commit()
    return conn


def test_connect_enables_wal(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode is not None
        assert str(mode[0]).lower() == "wal"
    finally:
        conn.close()


def test_migrations_are_numbered_and_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "kronos.sqlite3"
    conn = connect(db)
    try:
        apply_migrations(conn)
        apply_migrations(conn)
        versions = [
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        assert versions == sorted(set(versions))
    finally:
        conn.close()


def test_control_plane_tables_exist(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    try:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "schema_migrations",
            "events",
            "outbox",
            "leases",
            "repositories",
            "goals",
            "model_providers",
            "model_profiles",
            "model_assignments",
            "github_apps",
            "tasks",
            "runs",
            "budget_meters",
            "task_attempts",
            "skills",
            "memory_records",
            "telegram_settings",
            "telegram_updates",
            "telegram_rate",
            "dead_letters",
            "ops_settings",
            "ops_degradation",
            "conversations",
            "conversation_messages",
            "chat_file_backups",
        } <= names
    finally:
        conn.close()


def test_migration_11_upgrades_a_v10_database_with_rows(tmp_path: Path) -> None:
    conn = _open_at_version(tmp_path / "kronos.sqlite3", 10)
    try:
        conn.execute(
            "INSERT INTO repositories("
            "id, realpath, origin, display_name, status, policy_json, enrolled_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("repo_1", str(tmp_path), None, "repo", "active", "{}", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO conversations(id, repository_id, title, created_at) VALUES (?, ?, ?, ?)",
            ("conv_1", "repo_1", "Old", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO conversation_messages("
            "id, conversation_id, role, content, citations_json, goal_refs_json,"
            " model, token_count, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg_1", "conv_1", "user", "hello", "[]", "[]", None, None, "2026-01-01T00:00:01Z"),
        )
        conn.commit()

        apply_migrations(conn)

        versions = [
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

        conversation = conn.execute(
            "SELECT repository_id, title FROM conversations WHERE id = ?", ("conv_1",)
        ).fetchone()
        assert conversation is not None
        assert conversation["repository_id"] == "repo_1"
        assert conversation["title"] == "Old"

        message = conn.execute(
            "SELECT role, content, tool_name, tool_status, tool_json "
            "FROM conversation_messages WHERE id = ?",
            ("msg_1",),
        ).fetchone()
        assert message is not None
        assert message["role"] == "user"
        assert message["content"] == "hello"
        assert message["tool_name"] is None
        assert message["tool_status"] is None
        assert message["tool_json"] is None

        conn.execute(
            "INSERT INTO conversations(id, repository_id, title, created_at) VALUES (?, ?, ?, ?)",
            ("conv_2", None, "No repo", "2026-01-02T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO conversation_messages("
            "id, conversation_id, role, content, citations_json, goal_refs_json,"
            " model, token_count, created_at, tool_name, tool_status, tool_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "msg_2",
                "conv_2",
                "tool",
                "read_file",
                "[]",
                "[]",
                None,
                None,
                "2026-01-02T00:00:01Z",
                "read_file",
                "ok",
                '{"path": "README.md"}',
            ),
        )
        conn.commit()

        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "chat_file_backups" in names
        indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        assert "idx_conversations_repository_id" in indexes
        assert "idx_conversation_messages_conversation_id" in indexes
    finally:
        conn.close()
