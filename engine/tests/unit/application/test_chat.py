# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kronos_engine.application.chat import (
    ChatService,
    ChatTurn,
    ChatTurnCancelled,
    request_cancel,
)
from kronos_engine.domain.entities import EnrolledRepository, RepositoryId, RepositoryStatus
from kronos_engine.domain.policy import default_policy
from kronos_engine.memory.procedural import persist_record
from kronos_engine.memory.records import MemoryKind, MemoryRecord, MemoryStatus
from kronos_engine.state.chat import SqliteChatStore
from kronos_engine.state.database import Database


class ScriptedCompleter:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[tuple[tuple[ChatTurn, ...], str]] = []

    def complete(
        self,
        turns: Sequence[ChatTurn],
        system: str,
        *,
        cancel: object = None,
        on_delta: object = None,
    ) -> str:
        _ = cancel, on_delta
        self.prompts.append((tuple(turns), system))
        return self.replies.pop(0)


def _service(tmp_path: Path, replies: list[str]) -> ChatService:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    return ChatService(SqliteChatStore(conn), ScriptedCompleter(replies))


def test_send_message_stores_user_and_assistant_turns(tmp_path: Path) -> None:
    service = _service(tmp_path, ["Staff is missing before the calendar route."])
    session = service.create_session()
    messages = service.send_message(session.id, "What is broken in onboarding?")
    roles = [item.role for item in messages]
    assert roles == ["user", "assistant"]
    assert messages[0].content == "What is broken in onboarding?"
    assert "calendar" in messages[1].content
    listed = service.list_sessions()
    assert listed[0].title.startswith("What is broken")


def test_tool_round_records_search_then_final_answer(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [
            '```tool\n{"name": "search_index", "query": "onboarding"}\n```',
            "No index hits yet. Open a git folder.",
        ],
    )
    session = service.create_session()
    messages = service.send_message(session.id, "Search the workspace.")
    assert [item.role for item in messages] == ["user", "tool", "assistant"]
    assert messages[1].tool_name == "search_index"
    assert "Open a git folder" in messages[2].content or (
        "Index is not available" in messages[1].content
    )


class _CancelDuringComplete:
    def __init__(self, session_id: str, reply: str) -> None:
        self.session_id = session_id
        self.reply = reply
        self.calls = 0

    def complete(
        self,
        turns: Sequence[ChatTurn],
        system: str,
        *,
        cancel: object = None,
        on_delta: object = None,
    ) -> str:
        _ = turns, system, cancel, on_delta
        self.calls += 1
        request_cancel(self.session_id)
        return self.reply


class _RepoLookup:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, repository_id: RepositoryId) -> EnrolledRepository:
        return EnrolledRepository(
            id=repository_id,
            realpath=str(self._root),
            origin=None,
            display_name="alpha",
            status=RepositoryStatus.ACTIVE,
            policy=default_policy(integration_branch="main", protected_branch="main"),
            enrolled_at="t",
        )


def test_cancel_stops_before_running_more_tools(tmp_path: Path) -> None:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    service = ChatService(SqliteChatStore(conn), ScriptedCompleter(["placeholder"]))
    session = service.create_session()
    completer = _CancelDuringComplete(
        session.id,
        '```tool\n{"name": "list_goals"}\n```',
    )
    service = ChatService(SqliteChatStore(conn), completer)
    messages = service.send_message(session.id, "Start work")
    assert completer.calls == 1
    assert not any(item.role == "tool" for item in messages)
    assert any("Stopped" in item.content for item in messages if item.role == "assistant")


def test_write_file_stays_inside_workspace_and_rejects_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("old\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(
            [
                '```tool\n{"name": "write_file", "path": "hello.py", "content": "new\\n"}\n```',
                "Updated hello.py.",
            ]
        ),
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    messages = service.send_message(session.id, "Patch hello.py", repository_id="repo_alpha")
    assert (repo / "hello.py").read_text(encoding="utf-8") == "new\n"
    assert any(item.tool_name == "write_file" and item.tool_status == "ok" for item in messages)

    escaped = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(
            [
                '```tool\n{"name": "write_file", "path": "../secret.txt", "content": "nope"}\n```',
                "I will not write outside the folder.",
            ]
        ),
        repos=_RepoLookup(repo),
    )
    escaped.send_message(session.id, "Escape", repository_id="repo_alpha")
    assert not (tmp_path / "secret.txt").exists()


def test_active_memories_are_injected_into_the_system_prompt(tmp_path: Path) -> None:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    persist_record(
        conn,
        MemoryRecord(
            id="mem-staff",
            kind=MemoryKind.procedural.value,
            text="Never send onboarding to the calendar before staff exists.",
            source_sha="abc",
            outcome="neutral",
            confidence=0.8,
            helpful=2,
            harmful=0,
            status=MemoryStatus.active,
            independent_sources=("abc",),
            skill_id=None,
            created_at="2026-09-01T00:00:00+00:00",
            provenance={},
        ),
        None,
    )
    conn.commit()
    completer = ScriptedCompleter(["I will guard the calendar route."])
    service = ChatService(SqliteChatStore(conn), completer, memory_conn=conn)
    session = service.create_session()
    service.send_message(session.id, "Fix onboarding")
    system = completer.prompts[0][1]
    assert "Never send onboarding to the calendar" in system


_STREAM_SNAPSHOTS: list[tuple[str, ...]] = []


def _stream_and_snapshot(store: SqliteChatStore, session_id: str, on_delta: object) -> str:
    if not callable(on_delta):
        raise AssertionError("chat must stream tokens through on_delta")
    on_delta("partial-token")
    snapshot = tuple(item.content for item in store.list_messages(session_id))
    _STREAM_SNAPSHOTS.append(snapshot)
    return "partial-token and more"


def test_send_persists_streamed_tokens_before_complete_returns(tmp_path: Path) -> None:
    _STREAM_SNAPSHOTS.clear()
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    store = SqliteChatStore(conn)

    class Streamer:
        def complete(
            self,
            turns: Sequence[ChatTurn],
            system: str,
            *,
            cancel: object = None,
            on_delta: object = None,
        ) -> str:
            _ = turns, system, cancel
            return _stream_and_snapshot(store, session.id, on_delta)

    service = ChatService(store, Streamer())
    session = service.create_session()
    messages = service.send_message(session.id, "Hi")
    assert _STREAM_SNAPSHOTS
    assert any("partial-token" in item for item in _STREAM_SNAPSHOTS[0])
    assert messages[-1].content == "partial-token and more"
    assert messages[-1].tool_status is None


def test_cancel_during_stream_keeps_partial_and_stops(tmp_path: Path) -> None:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    store = SqliteChatStore(conn)

    class StreamThenCancel:
        def complete(
            self,
            turns: Sequence[ChatTurn],
            system: str,
            *,
            cancel: object = None,
            on_delta: object = None,
        ) -> str:
            _ = turns, system
            if callable(on_delta):
                on_delta("Hi from the model")
            request_cancel(session.id)
            raise ChatTurnCancelled("Hi from the model")

    service = ChatService(store, StreamThenCancel())
    session = service.create_session()
    messages = service.send_message(session.id, "Go")
    assistant = [item for item in messages if item.role == "assistant"]
    assert assistant
    assert "Hi from the model" in assistant[-1].content
    assert "Stopped" in assistant[-1].content
    assert not any(item.role == "tool" for item in messages)
