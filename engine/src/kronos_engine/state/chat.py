# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite persistence for desktop agent chats."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatSessionRow:
    id: str
    title: str
    repository_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ChatMessageRow:
    id: str
    session_id: str
    role: str
    content: str
    tool_name: str | None
    tool_status: str | None
    created_at: str
    seq: int


class SqliteChatStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_session(self, row: ChatSessionRow) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_sessions(id, title, repository_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                repository_id = excluded.repository_id,
                updated_at = excluded.updated_at
            """,
            (row.id, row.title, row.repository_id, row.created_at, row.updated_at),
        )
        self._conn.commit()

    def get_session(self, session_id: str) -> ChatSessionRow:
        row = self._conn.execute(
            "SELECT id, title, repository_id, created_at, updated_at "
            "FROM chat_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"chat session not found: {session_id}")
        return _session_from_row(row)

    def list_sessions(self) -> Sequence[ChatSessionRow]:
        rows = self._conn.execute(
            "SELECT id, title, repository_id, created_at, updated_at "
            "FROM chat_sessions ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        return tuple(_session_from_row(item) for item in rows)

    def append_message(self, row: ChatMessageRow) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_messages(
                id, session_id, role, content, tool_name, tool_status, created_at, seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.id,
                row.session_id,
                row.role,
                row.content,
                row.tool_name,
                row.tool_status,
                row.created_at,
                row.seq,
            ),
        )
        self._conn.commit()

    def update_message(
        self, message_id: str, *, content: str, tool_status: str | None
    ) -> None:
        self._conn.execute(
            "UPDATE chat_messages SET content = ?, tool_status = ? WHERE id = ?",
            (content, tool_status, message_id),
        )
        self._conn.commit()

    def delete_message(self, message_id: str) -> None:
        self._conn.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))
        self._conn.commit()

    def list_messages(self, session_id: str) -> Sequence[ChatMessageRow]:
        rows = self._conn.execute(
            "SELECT id, session_id, role, content, tool_name, tool_status, created_at, seq "
            "FROM chat_messages WHERE session_id = ? ORDER BY seq, id",
            (session_id,),
        ).fetchall()
        return tuple(_message_from_row(item) for item in rows)

    def next_seq(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM chat_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        current = int(row[0]) if row is not None else 0
        return current + 1

    def save_file_backup(self, repository_id: str, path: str, before: str, created_at: str) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_file_backups(repository_id, path, before, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(repository_id, path) DO UPDATE SET
                before = excluded.before,
                created_at = excluded.created_at
            """,
            (repository_id, path, before, created_at),
        )
        self._conn.commit()

    def get_file_backup(self, repository_id: str, path: str) -> str | None:
        row = self._conn.execute(
            "SELECT before FROM chat_file_backups WHERE repository_id = ? AND path = ?",
            (repository_id, path),
        ).fetchone()
        if row is None:
            return None
        return str(row["before"])

    def delete_file_backup(self, repository_id: str, path: str) -> None:
        self._conn.execute(
            "DELETE FROM chat_file_backups WHERE repository_id = ? AND path = ?",
            (repository_id, path),
        )
        self._conn.commit()


def _session_from_row(row: sqlite3.Row) -> ChatSessionRow:
    return ChatSessionRow(
        id=row["id"],
        title=row["title"],
        repository_id=row["repository_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _message_from_row(row: sqlite3.Row) -> ChatMessageRow:
    return ChatMessageRow(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        tool_name=row["tool_name"],
        tool_status=row["tool_status"],
        created_at=row["created_at"],
        seq=int(row["seq"]),
    )
