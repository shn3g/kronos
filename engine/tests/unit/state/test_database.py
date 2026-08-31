# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from kronos_engine.state.database import Database, connect


def test_connect_rejects_use_from_another_thread(tmp_path: Path) -> None:
    conn = connect(tmp_path / "kronos.sqlite3")
    errors: list[BaseException] = []

    def use_from_other_thread() -> None:
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError as error:
            errors.append(error)

    try:
        thread = threading.Thread(target=use_from_other_thread)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert errors
    finally:
        conn.close()


def test_database_opens_a_distinct_connection_per_call(tmp_path: Path) -> None:
    database = Database(tmp_path / "kronos.sqlite3")
    first = database.connect()
    second = database.connect()
    try:
        assert first is not second
        first.execute("SELECT 1")
        second.execute("SELECT 1")
    finally:
        first.close()
        second.close()
