# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite connection helpers. WAL is required."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kronos_engine.state.migrations import apply_migrations


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
    if mode is None or str(mode[0]).lower() != "wal":
        conn.close()
        raise RuntimeError("SQLite WAL mode is required")
    apply_migrations(conn)
    return conn
