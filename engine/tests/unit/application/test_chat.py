# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from tests.support.git_fixtures import init_git_repo

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


class _WriteEvents:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict[str, object]]] = []

    def emit(self, event_type: str, payload: dict[str, object]) -> None:
        self.items.append((event_type, dict(payload)))


def test_write_file_records_a_workspace_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("old\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    events = _WriteEvents()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(
            [
                '```tool\n{"name": "write_file", "path": "hello.py", "content": "new\\n"}\n```',
                "Updated hello.py.",
            ]
        ),
        repos=_RepoLookup(repo),
        events=events,
    )
    session = service.create_session()
    service.send_message(session.id, "Patch hello.py", repository_id="repo_alpha")
    assert events.items
    kind, payload = events.items[0]
    assert kind == "git.wrote"
    assert payload["path"] == "hello.py"
    assert payload["repository_id"] == "repo_alpha"
    assert "hello.py" in str(payload["summary"])
    patch = str(payload["patch"])
    assert "-old" in patch
    assert "+new" in patch


def test_revert_write_restores_previous_file_contents(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("old\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    events = _WriteEvents()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(
            [
                '```tool\n{"name": "write_file", "path": "hello.py", "content": "new\\n"}\n```',
                "Updated hello.py.",
            ]
        ),
        repos=_RepoLookup(repo),
        events=events,
    )
    session = service.create_session()
    service.send_message(session.id, "Patch hello.py", repository_id="repo_alpha")
    assert (repo / "hello.py").read_text(encoding="utf-8") == "new\n"
    service.revert_write("repo_alpha", "hello.py")
    assert (repo / "hello.py").read_text(encoding="utf-8") == "old\n"
    assert events.items[-1][0] == "git.reverted"
    assert events.items[-1][1]["path"] == "hello.py"


def test_revert_write_deletes_a_file_created_by_chat(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(
            [
                '```tool\n{"name": "write_file", "path": "fresh.py", "content": "hi\\n"}\n```',
                "Created fresh.py.",
            ]
        ),
        repos=_RepoLookup(repo),
        events=_WriteEvents(),
    )
    session = service.create_session()
    service.send_message(session.id, "Add fresh.py", repository_id="repo_alpha")
    assert (repo / "fresh.py").is_file()
    service.revert_write("repo_alpha", "fresh.py")
    assert not (repo / "fresh.py").exists()


def test_revert_write_rejects_unknown_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(["ok"]),
        repos=_RepoLookup(repo),
        events=_WriteEvents(),
    )
    try:
        service.revert_write("repo_alpha", "missing.py")
    except ValueError as error:
        assert "revert" in str(error).lower() or "write" in str(error).lower()
    else:
        raise AssertionError("expected revert of an unknown path to fail")


def test_revert_write_restores_head_when_there_is_no_chat_backup(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    (repo / "hello.py").write_text("local\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(["ok"]),
        repos=_RepoLookup(repo),
        events=_WriteEvents(),
    )

    service.revert_write("repo_alpha", "hello.py")

    assert (repo / "hello.py").read_text(encoding="utf-8") == "old\n"


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


def test_send_message_attaches_mentioned_file_to_system_prompt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("print('ok')\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    completer = ScriptedCompleter(["Looks fine."])
    service = ChatService(
        SqliteChatStore(conn),
        completer,
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    service.send_message(session.id, "Review @hello.py", repository_id="repo_alpha")
    _turns, system = completer.prompts[0]
    assert "hello.py" in system
    assert "print('ok')" in system


def test_send_message_does_not_attach_escaped_mention(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "secret.txt").write_text("nope\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    completer = ScriptedCompleter(["Denied."])
    service = ChatService(
        SqliteChatStore(conn),
        completer,
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    service.send_message(session.id, "See @../secret.txt", repository_id="repo_alpha")
    _turns, system = completer.prompts[0]
    assert "nope" not in system


def _python_script(root: Path, name: str, source: str) -> str:
    (root / name).write_text(source, encoding="utf-8")
    return f'"{sys.executable}" {name}'


def test_run_command_uses_workspace_cwd_and_needs_a_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "marker.txt").write_text("from-workspace\n", encoding="utf-8")
    command = _python_script(
        repo,
        "probe.py",
        "from pathlib import Path\nprint(Path('marker.txt').read_text())\n",
    )
    fence = "```tool\n" + json.dumps({"name": "run_command", "command": command}) + "\n```"
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(
            [
                fence,
                "The marker is in the workspace.",
            ]
        ),
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    messages = service.send_message(session.id, "Run probe.py", repository_id="repo_alpha")
    tool = next(item for item in messages if item.tool_name == "run_command")
    assert tool.tool_status == "ok"
    assert "from-workspace" in tool.content
    assert "Exit 0" in tool.content

    blank = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter(
            [
                '```tool\n{"name": "run_command", "command": "   "}\n```',
                "I need a command.",
            ]
        ),
        repos=_RepoLookup(repo),
    )
    blank_messages = blank.send_message(session.id, "Empty command", repository_id="repo_alpha")
    blank_tool = [item for item in blank_messages if item.tool_name == "run_command"][-1]
    assert "command is required" in blank_tool.content.lower()


def test_run_command_needs_an_open_workspace(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [
            '```tool\n{"name": "run_command", "command": "echo hi"}\n```',
            "Open a folder first.",
        ],
    )
    session = service.create_session()
    messages = service.send_message(session.id, "Run echo")
    tool = next(item for item in messages if item.tool_name == "run_command")
    assert "git folder" in tool.content.lower()


def test_run_command_caps_how_many_commands_run_in_one_turn(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    command = _python_script(
        repo,
        "tick.py",
        "from pathlib import Path\n"
        "p = Path('ticks.txt')\n"
        "prior = p.read_text(encoding='utf-8') if p.exists() else ''\n"
        "p.write_text(prior + 'x', encoding='utf-8')\n",
    )
    fence = "```tool\n" + json.dumps({"name": "run_command", "command": command}) + "\n```"
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    service = ChatService(
        SqliteChatStore(conn),
        ScriptedCompleter([fence, fence, fence, fence, "Done."]),
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    messages = service.send_message(session.id, "Tick four times", repository_id="repo_alpha")
    assert (repo / "ticks.txt").read_text(encoding="utf-8") == "xxx"
    tool_bodies = [item.content for item in messages if item.tool_name == "run_command"]
    assert any("3 commands" in body for body in tool_bodies)


def test_send_message_attaches_workspace_instructions_to_system_prompt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("Never commit to main.\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_text("Nested secret rule.\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    completer = ScriptedCompleter(["Understood."])
    service = ChatService(
        SqliteChatStore(conn),
        completer,
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    service.send_message(session.id, "What should I remember?", repository_id="repo_alpha")
    _turns, system = completer.prompts[0]
    assert "Workspace instructions:" in system
    assert "AGENTS.md" in system
    assert "Never commit to main." in system
    assert "Nested secret rule." not in system


def test_send_message_attaches_cursor_rule_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    rules = repo / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "python.mdc").write_text("Use type hints.\n", encoding="utf-8")
    (repo / ".cursorrules").write_text("No em dashes in UI copy.\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    completer = ScriptedCompleter(["Understood."])
    service = ChatService(
        SqliteChatStore(conn),
        completer,
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    service.send_message(session.id, "How should I write code?", repository_id="repo_alpha")
    _turns, system = completer.prompts[0]
    assert "No em dashes in UI copy." in system
    assert "Use type hints." in system
    assert ".cursor/rules/python.mdc" in system


def test_send_message_omits_workspace_instructions_when_none_exist(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    completer = ScriptedCompleter(["Hello."])
    service = ChatService(
        SqliteChatStore(conn),
        completer,
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    service.send_message(session.id, "Hi", repository_id="repo_alpha")
    _turns, system = completer.prompts[0]
    assert "Workspace instructions:" not in system


def test_send_message_skips_nested_cursor_rule_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    rules = repo / ".cursor" / "rules"
    nested = rules / "team"
    nested.mkdir(parents=True)
    (nested / "extra.md").write_text("Do not include nested.\n", encoding="utf-8")
    (rules / "root.md").write_text("Keep this.\n", encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    completer = ScriptedCompleter(["Understood."])
    service = ChatService(
        SqliteChatStore(conn),
        completer,
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    service.send_message(session.id, "Which rules apply?", repository_id="repo_alpha")
    _turns, system = completer.prompts[0]
    assert "Keep this." in system
    assert "Do not include nested." not in system


def test_send_message_caps_workspace_instruction_size(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("A" * 50_000, encoding="utf-8")
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    completer = ScriptedCompleter(["Trimmed."])
    service = ChatService(
        SqliteChatStore(conn),
        completer,
        repos=_RepoLookup(repo),
    )
    session = service.create_session()
    service.send_message(session.id, "Go", repository_id="repo_alpha")
    _turns, system = completer.prompts[0]
    assert system.count("A") <= 12_000
    assert "Workspace instructions:" in system
