# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite Telegram allowlist, offsets, and rate windows. Tokens never belong here."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class TelegramSettings:
    allowed_user_ids: frozenset[int]
    allowed_chat_ids: frozenset[int]
    default_repository_id: str | None
    last_update_offset: int


class SqliteTelegramStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_row()

    def load(self) -> TelegramSettings:
        row = self._conn.execute(
            "SELECT allowed_user_ids_json, allowed_chat_ids_json, "
            "default_repository_id, last_update_offset FROM telegram_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return TelegramSettings(frozenset(), frozenset(), None, 0)
        users = json.loads(row["allowed_user_ids_json"])
        chats = json.loads(row["allowed_chat_ids_json"])
        return TelegramSettings(
            allowed_user_ids=frozenset(int(item) for item in users),
            allowed_chat_ids=frozenset(int(item) for item in chats),
            default_repository_id=row["default_repository_id"],
            last_update_offset=int(row["last_update_offset"]),
        )

    def save_allowlist(
        self,
        user_ids: tuple[int, ...] | list[int],
        chat_ids: tuple[int, ...] | list[int],
        *,
        default_repository_id: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO telegram_settings(
                id, allowed_user_ids_json, allowed_chat_ids_json,
                default_repository_id, last_update_offset
            ) VALUES (1, ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                allowed_user_ids_json = excluded.allowed_user_ids_json,
                allowed_chat_ids_json = excluded.allowed_chat_ids_json,
                default_repository_id = excluded.default_repository_id
            """,
            (
                json.dumps([int(item) for item in user_ids]),
                json.dumps([int(item) for item in chat_ids]),
                default_repository_id,
            ),
        )
        self._conn.commit()

    def seen(self, update_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM telegram_updates WHERE update_id = ?",
            (update_id,),
        ).fetchone()
        return row is not None

    def commit_update(self, update_id: int) -> None:
        now = datetime.now(tz=UTC).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO telegram_updates(update_id, processed_at) VALUES (?, ?)",
            (update_id, now),
        )
        current = self.load().last_update_offset
        nxt = update_id + 1
        if nxt > current:
            self._conn.execute(
                "UPDATE telegram_settings SET last_update_offset = ? WHERE id = 1",
                (nxt,),
            )
        self._conn.commit()

    def allow_request(
        self,
        user_id: int,
        now: float,
        *,
        approval: bool,
        command_limit: int,
        approval_limit: int,
        window_seconds: float,
    ) -> bool:
        window = int(now // window_seconds) * int(window_seconds)
        row = self._conn.execute(
            "SELECT command_count, approval_count FROM telegram_rate "
            "WHERE user_id = ? AND window_start = ?",
            (user_id, window),
        ).fetchone()
        command_count = int(row["command_count"]) if row is not None else 0
        approval_count = int(row["approval_count"]) if row is not None else 0
        if approval:
            if approval_count >= approval_limit:
                return False
            approval_count += 1
        else:
            if command_count >= command_limit:
                return False
            command_count += 1
        self._conn.execute(
            """
            INSERT INTO telegram_rate(user_id, window_start, command_count, approval_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, window_start) DO UPDATE SET
                command_count = excluded.command_count,
                approval_count = excluded.approval_count
            """,
            (user_id, window, command_count, approval_count),
        )
        self._conn.commit()
        return True

    def _ensure_row(self) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO telegram_settings(
                id, allowed_user_ids_json, allowed_chat_ids_json,
                default_repository_id, last_update_offset
            ) VALUES (1, '[]', '[]', NULL, 0)
            """
        )
        self._conn.commit()
