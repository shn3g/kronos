# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite persistence for orchestrator conversations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: str
    repository_id: str | None
    title: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    id: str
    conversation_id: str
    role: str
    content: str
    citations: tuple[dict[str, object], ...]
    goal_refs: tuple[str, ...]
    model: str | None
    token_count: int | None
    created_at: str
    tool_name: str | None = None
    tool_status: str | None = None
    tool_json: str | None = None


class SqliteConversationStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, repository_id: str | None, title: str) -> ConversationRecord:
        record = ConversationRecord(
            id=f"conv_{uuid4().hex[:16]}",
            repository_id=repository_id,
            title=title,
            created_at=datetime.now(tz=UTC).isoformat(),
        )
        self._conn.execute(
            "INSERT INTO conversations(id, repository_id, title, created_at) VALUES (?, ?, ?, ?)",
            (record.id, record.repository_id, record.title, record.created_at),
        )
        self._conn.commit()
        return record

    def get(self, conversation_id: str) -> ConversationRecord:
        row = self._conn.execute(
            "SELECT id, repository_id, title, created_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"conversation not found: {conversation_id}")
        return ConversationRecord(
            id=row["id"],
            repository_id=row["repository_id"],
            title=row["title"],
            created_at=row["created_at"],
        )

    def list_for_repository(self, repository_id: str | None) -> Sequence[ConversationRecord]:
        if repository_id is None:
            rows = self._conn.execute(
                "SELECT id, repository_id, title, created_at FROM conversations "
                "WHERE repository_id IS NULL ORDER BY created_at, id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, repository_id, title, created_at FROM conversations "
                "WHERE repository_id = ? ORDER BY created_at, id",
                (repository_id,),
            ).fetchall()
        return tuple(
            ConversationRecord(
                id=row["id"],
                repository_id=row["repository_id"],
                title=row["title"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def delete(self, conversation_id: str) -> None:
        self.get(conversation_id)
        self._conn.execute(
            "DELETE FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        self._conn.commit()

    def add_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        citations: Sequence[dict[str, object]] = (),
        goal_refs: Sequence[str] = (),
        model: str | None = None,
        token_count: int | None = None,
        message_id: str | None = None,
        tool_name: str | None = None,
        tool_status: str | None = None,
        tool_json: str | None = None,
    ) -> ConversationMessage:
        record = ConversationMessage(
            id=message_id or f"msg_{uuid4().hex[:16]}",
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=tuple(dict(item) for item in citations),
            goal_refs=tuple(goal_refs),
            model=model,
            token_count=token_count,
            created_at=datetime.now(tz=UTC).isoformat(),
            tool_name=tool_name,
            tool_status=tool_status,
            tool_json=tool_json,
        )
        self._conn.execute(
            """
            INSERT INTO conversation_messages(
                id, conversation_id, role, content, citations_json, goal_refs_json,
                model, token_count, created_at, tool_name, tool_status, tool_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.conversation_id,
                record.role,
                record.content,
                json.dumps(list(record.citations)),
                json.dumps(list(record.goal_refs)),
                record.model,
                record.token_count,
                record.created_at,
                record.tool_name,
                record.tool_status,
                record.tool_json,
            ),
        )
        self._conn.commit()
        return record

    def list_messages(self, conversation_id: str) -> Sequence[ConversationMessage]:
        rows = self._conn.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? "
            "ORDER BY created_at, id",
            (conversation_id,),
        ).fetchall()
        return tuple(_message_from_row(row) for row in rows)

    def save_file_backup(
        self, repository_id: str, path: str, before: str, created_at: str
    ) -> None:
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

    def list_backup_paths(self, repository_id: str) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT path FROM chat_file_backups WHERE repository_id = ? ORDER BY path",
            (repository_id,),
        ).fetchall()
        return tuple(str(row["path"]) for row in rows)


def _message_from_row(row: sqlite3.Row) -> ConversationMessage:
    citations_raw: object = json.loads(row["citations_json"])
    refs_raw: object = json.loads(row["goal_refs_json"])
    citations: list[dict[str, object]] = []
    if isinstance(citations_raw, list):
        citations = [item for item in citations_raw if isinstance(item, dict)]
    refs: list[str] = []
    if isinstance(refs_raw, list):
        refs = [str(item) for item in refs_raw]
    token_count = row["token_count"]
    return ConversationMessage(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        citations=tuple(citations),
        goal_refs=tuple(refs),
        model=row["model"],
        token_count=int(token_count) if token_count is not None else None,
        created_at=row["created_at"],
        tool_name=row["tool_name"],
        tool_status=row["tool_status"],
        tool_json=row["tool_json"],
    )
