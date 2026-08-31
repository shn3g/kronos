# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite connection helpers. WAL is required."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kronos_engine.state.migrations import apply_migrations


def connect(path: Path) -> sqlite3.Connection:
    return _open(path, migrate=True)


def _open(path: Path, *, migrate: bool) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
    if mode is None or str(mode[0]).lower() != "wal":
        conn.close()
        raise RuntimeError("SQLite WAL mode is required")
    if migrate:
        apply_migrations(conn)
    return conn


class Database:
    """One SQLite file. Each connect() is for a single thread/unit of work."""

    def __init__(self, path: Path) -> None:
        self._path = path
        bootstrap = connect(path)
        bootstrap.close()

    def connect(self) -> sqlite3.Connection:
        return _open(self._path, migrate=False)
