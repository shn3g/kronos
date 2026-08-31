# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from kronos_engine.state.database import connect
from kronos_engine.state.migrations import apply_migrations


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
        assert versions == [1, 2, 3, 4, 5, 6, 7]
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
        } <= names
    finally:
        conn.close()
