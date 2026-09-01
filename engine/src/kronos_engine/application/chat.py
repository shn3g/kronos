# SPDX-License-Identifier: AGPL-3.0-or-later
"""Desktop agent chat. Tools stay inside enrolled repository roots."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from typing import Protocol
from uuid import uuid4

from kronos_engine.application.chat_diff import unified_write_patch
from kronos_engine.application.chat_mentions import mentioned_workspace_paths
from kronos_engine.application.chat_tools import ToolCall, ToolParseError, parse_tool_call
from kronos_engine.application.goals import GoalService
from kronos_engine.application.repositories import RepositoryNotFound, RepositoryService
from kronos_engine.domain.entities import RepositoryId
from kronos_engine.domain.goals import GoalSource, GoalSpec
from kronos_engine.indexing.service import IndexingService
from kronos_engine.memory.procedural import retrieve_records
from kronos_engine.state.chat import ChatMessageRow, ChatSessionRow, SqliteChatStore

MAX_TOOL_ROUNDS = 6
MAX_WRITE_CHARS = 200_000
STOP_MESSAGE = "Stopped. Ask again when you want to continue."
SYSTEM_PROMPT = """You are Kronos, a locally installed coding agent. Answer in plain language.
When you need a tool, emit only a fenced JSON block:

```tool
{"name": "search_index", "query": "onboarding"}
```

Tools: search_index (query), read_file (path), write_file (path, content),
search_memory (query), create_goal (title, success_criteria), list_goals.
Stay inside the current workspace. Do not claim you edited files unless write_file succeeded.
If you do not need a tool, reply without a tool fence."""

_CANCEL: dict[str, Event] = {}
_CANCEL_LOCK = Lock()


def _cancel_event(session_id: str) -> Event:
    with _CANCEL_LOCK:
        return _CANCEL.setdefault(session_id, Event())


def request_cancel(session_id: str) -> None:
    _cancel_event(session_id).set()


class ChatCompleter(Protocol):
    def complete(
        self,
        turns: Sequence[ChatTurn],
        system: str,
        *,
        cancel: Event | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> str: ...


class ChatEventSink(Protocol):
    def emit(self, event_type: str, payload: Mapping[str, object]) -> object: ...


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: str
    content: str


class ChatModelError(RuntimeError):
    """Raised when no usable model is assigned."""


class ChatTurnCancelled(RuntimeError):
    """Raised when Stop aborts an in-flight model completion."""

    def __init__(self, partial: str) -> None:
        super().__init__("chat turn cancelled")
        self.partial = partial


@dataclass(frozen=True, slots=True)
class ChatSessionView:
    id: str
    title: str
    repository_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ChatMessageView:
    id: str
    role: str
    content: str
    tool_name: str | None
    tool_status: str | None
    created_at: str


class ChatService:
    def __init__(
        self,
        store: SqliteChatStore,
        completer: ChatCompleter,
        *,
        repos: RepositoryService | None = None,
        indexer: IndexingService | None = None,
        goals: GoalService | None = None,
        clock: datetime | None = None,
        memory_conn: sqlite3.Connection | None = None,
        events: ChatEventSink | None = None,
    ) -> None:
        self._store = store
        self._completer = completer
        self._repos = repos
        self._indexer = indexer
        self._goals = goals
        self._clock = clock
        self._memory_conn = memory_conn
        self._events = events

    def create_session(self, *, repository_id: str | None = None) -> ChatSessionView:
        now = self._now()
        row = ChatSessionRow(
            id=f"chat_{uuid4().hex[:16]}",
            title="New chat",
            repository_id=repository_id,
            created_at=now,
            updated_at=now,
        )
        self._store.save_session(row)
        return _session_view(row)

    def list_sessions(self) -> Sequence[ChatSessionView]:
        return tuple(_session_view(item) for item in self._store.list_sessions())

    def get(self, session_id: str) -> tuple[ChatSessionView, tuple[ChatMessageView, ...]]:
        session = _session_view(self._store.get_session(session_id))
        messages = tuple(_message_view(item) for item in self._store.list_messages(session_id))
        return session, messages

    def send_message(
        self,
        session_id: str,
        content: str,
        *,
        repository_id: str | None = None,
    ) -> tuple[ChatMessageView, ...]:
        text = content.strip()
        if text == "":
            raise ValueError("message is required")
        session = self._store.get_session(session_id)
        if repository_id:
            session = ChatSessionRow(
                id=session.id,
                title=_title_from(text, session.title),
                repository_id=repository_id,
                created_at=session.created_at,
                updated_at=self._now(),
            )
            self._store.save_session(session)
        elif session.title == "New chat":
            session = ChatSessionRow(
                id=session.id,
                title=_title_from(text, session.title),
                repository_id=session.repository_id,
                created_at=session.created_at,
                updated_at=self._now(),
            )
            self._store.save_session(session)
        self._append(
            session.id,
            role="user",
            content=text,
            tool_name=None,
            tool_status=None,
        )
        repo_id = repository_id or session.repository_id
        cancel = _cancel_event(session.id)
        cancel.clear()
        try:
            self._run_agent(session.id, repo_id, cancel)
        except ChatTurnCancelled as cancelled:
            self._record_stop(session.id, cancelled.partial)
        except ChatModelError:
            self._append(
                session.id,
                role="assistant",
                content="No model is connected. Add a model before chatting.",
                tool_name=None,
                tool_status=None,
            )
        except Exception:
            self._append(
                session.id,
                role="assistant",
                content=(
                    "The model could not finish this turn. "
                    "Check the model connection in Settings."
                ),
                tool_name=None,
                tool_status=None,
            )
        return tuple(_message_view(item) for item in self._store.list_messages(session.id))

    def _run_agent(self, session_id: str, repository_id: str | None, cancel: Event) -> None:
        for _ in range(MAX_TOOL_ROUNDS):
            if cancel.is_set():
                self._record_stop(session_id, "")
                return
            turns = tuple(
                ChatTurn(role=item.role, content=item.content)
                for item in self._store.list_messages(session_id)
            )
            try:
                reply, streaming_id = self._stream_reply(
                    session_id, turns, self._system_prompt(turns, repository_id), cancel
                )
            except ChatTurnCancelled:
                return
            if cancel.is_set():
                shown = _stop_partial(reply)
                self._record_stop(session_id, shown, streaming_id)
                return
            if self._finish_model_text(session_id, repository_id, reply, streaming_id):
                return
        self._append(
            session_id,
            role="assistant",
            content="Stopped after too many tool steps. Ask again with a smaller request.",
            tool_name=None,
            tool_status=None,
        )

    def _stream_reply(
        self,
        session_id: str,
        turns: Sequence[ChatTurn],
        system: str,
        cancel: Event,
    ) -> tuple[str, str | None]:
        chunks: list[str] = []
        message_id: str | None = None

        def on_delta(chunk: str) -> None:
            nonlocal message_id
            chunks.append(chunk)
            message_id = self._upsert_stream(session_id, message_id, "".join(chunks))

        try:
            reply = self._invoke_complete(turns, system, cancel, on_delta)
        except ChatTurnCancelled as cancelled:
            self._record_stop(session_id, cancelled.partial or "".join(chunks), message_id)
            raise
        return reply, message_id

    def _invoke_complete(
        self,
        turns: Sequence[ChatTurn],
        system: str,
        cancel: Event,
        on_delta: Callable[[str], None],
    ) -> str:
        method = self._completer.complete
        return method(turns, system, cancel=cancel, on_delta=on_delta)

    def _finish_model_text(
        self,
        session_id: str,
        repository_id: str | None,
        reply: str,
        streaming_id: str | None,
    ) -> bool:
        try:
            call = parse_tool_call(reply)
        except ToolParseError as error:
            self._finalize_assistant(session_id, streaming_id, str(error), tool_status="error")
            return True
        if call is None:
            self._finalize_assistant(
                session_id, streaming_id, reply.strip() or "I had nothing to add.", None
            )
            return True
        if streaming_id is not None:
            self._store.delete_message(streaming_id)
        result = self._execute_tool(call, repository_id)
        self._append(
            session_id,
            role="tool",
            content=result,
            tool_name=call.name,
            tool_status="ok",
        )
        return False

    def _upsert_stream(self, session_id: str, message_id: str | None, content: str) -> str:
        if message_id is None:
            return self._append(
                session_id,
                role="assistant",
                content=content,
                tool_name=None,
                tool_status="streaming",
            )
        self._store.update_message(message_id, content=content, tool_status="streaming")
        return message_id

    def _finalize_assistant(
        self,
        session_id: str,
        message_id: str | None,
        content: str,
        tool_status: str | None,
    ) -> None:
        if message_id is None:
            self._append(
                session_id,
                role="assistant",
                content=content,
                tool_name=None,
                tool_status=tool_status,
            )
            return
        self._store.update_message(message_id, content=content, tool_status=tool_status)

    def _record_stop(
        self, session_id: str, partial: str, message_id: str | None = None
    ) -> None:
        body = STOP_MESSAGE if partial.strip() == "" else f"{partial.rstrip()}\n\n{STOP_MESSAGE}"
        self._finalize_assistant(session_id, message_id, body, None)

    def _execute_tool(self, call: ToolCall, repository_id: str | None) -> str:
        if call.name == "list_goals":
            return self._list_goals()
        if call.name == "search_memory":
            return self._search_memory(call.arguments.get("query", ""))
        if repository_id is None or repository_id == "":
            return "No workspace is open. Open a git folder first."
        if call.name == "search_index":
            return self._search_index(repository_id, call.arguments.get("query", ""))
        if call.name == "read_file":
            return self._read_file(repository_id, call.arguments.get("path", ""))
        if call.name == "write_file":
            return self._write_file(
                repository_id,
                call.arguments.get("path", ""),
                call.arguments.get("content", ""),
            )
        if call.name == "create_goal":
            return self._create_goal(repository_id, call.arguments)
        return "unknown tool"

    def _search_index(self, repository_id: str, query: str) -> str:
        if self._indexer is None:
            return "Index is not available."
        pack = self._indexer.search(repository_id, query)
        if not pack.items:
            return "No index hits. Rebuild the index after opening a workspace."
        lines = [
            f"{item.path}:{item.start_line}-{item.end_line} {item.text[:240]}"
            for item in pack.items[:8]
        ]
        return "\n".join(lines)

    def _read_file(self, repository_id: str, rel_path: str) -> str:
        if self._repos is None:
            return "Workspace is not available."
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return "Workspace was not found."
        root = Path(record.realpath).resolve()
        target = (root / rel_path).resolve()
        if not _is_inside(root, target) or not target.is_file():
            return "That path is outside the workspace or is not a file."
        text = target.read_text(encoding="utf-8", errors="replace")
        return text[:8000]

    def _write_file(self, repository_id: str, rel_path: str, content: str) -> str:
        if self._repos is None:
            return "Workspace is not available."
        if len(content) > MAX_WRITE_CHARS:
            return f"File is too large to write here. Keep it under {MAX_WRITE_CHARS} characters."
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return "Workspace was not found."
        root = Path(record.realpath).resolve()
        relative = Path(rel_path)
        if relative.is_absolute() or any(part == ".." or part == ".git" for part in relative.parts):
            return "That path is outside the workspace or is not a file."
        target = (root / relative).resolve()
        if not _is_inside(root, target):
            return "That path is outside the workspace or is not a file."
        locked = getattr(getattr(record, "policy", None), "paths", None)
        prefixes = getattr(locked, "locked_prefixes", ())
        as_posix = relative.as_posix()
        if any(
            as_posix == prefix.rstrip("/") or as_posix.startswith(prefix) for prefix in prefixes
        ):
            return "That path is locked by repository policy."
        target.parent.mkdir(parents=True, exist_ok=True)
        if not _is_inside(root, target.parent.resolve()):
            return "That path is outside the workspace or is not a file."
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        self._store.save_file_backup(repository_id, as_posix, before, self._now())
        target.write_text(content, encoding="utf-8")
        self._refresh_written_path(repository_id, root, record, as_posix)
        self._note_write(
            repository_id,
            as_posix,
            unified_write_patch(path=as_posix, before=before, after=content),
        )
        return f"Wrote {as_posix} ({len(content)} characters)."

    def _refresh_written_path(
        self, repository_id: str, root: Path, record: object, rel_path: str
    ) -> None:
        if self._indexer is None:
            return
        upsert = getattr(self._indexer, "upsert_working_paths", None)
        if not callable(upsert):
            return
        policy = getattr(record, "policy", None)
        if policy is None:
            return
        try:
            upsert(repository_id, root, policy, (rel_path,))
        except Exception:
            return

    def _note_write(self, repository_id: str, path: str, patch: str) -> None:
        if self._events is None:
            return
        try:
            self._events.emit(
                "git.wrote",
                {
                    "repository_id": repository_id,
                    "path": path,
                    "summary": f"Wrote {path}",
                    "patch": patch,
                },
            )
        except Exception:
            return

    def revert_write(self, repository_id: str, rel_path: str) -> None:
        if self._repos is None:
            raise ValueError("Workspace is not available.")
        relative = Path(rel_path)
        if rel_path.strip() == "" or relative.is_absolute() or any(
            part in {"..", ".git"} for part in relative.parts
        ):
            raise ValueError("That path is outside the workspace or is not a file.")
        as_posix = relative.as_posix()
        before = self._store.get_file_backup(repository_id, as_posix)
        if before is None:
            raise ValueError("No chat write to revert for that file.")
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError) as error:
            raise LookupError("Workspace was not found.") from error
        root = Path(record.realpath).resolve()
        target = (root / relative).resolve()
        if not _is_inside(root, target):
            raise ValueError("That path is outside the workspace or is not a file.")
        if before == "":
            if target.is_file():
                target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(before, encoding="utf-8")
        self._store.delete_file_backup(repository_id, as_posix)
        self._refresh_written_path(repository_id, root, record, as_posix)
        self._note_revert(repository_id, as_posix)

    def _note_revert(self, repository_id: str, path: str) -> None:
        if self._events is None:
            return
        try:
            self._events.emit(
                "git.reverted",
                {
                    "repository_id": repository_id,
                    "path": path,
                    "summary": f"Reverted {path}",
                },
            )
        except Exception:
            return

    def _search_memory(self, query: str) -> str:
        if self._memory_conn is None:
            return "Memories are not available."
        records = retrieve_records(self._memory_conn, query, None, limit=5)
        if not records:
            return "No matching memories."
        return "\n".join(item.text[:400] for item in records)

    def _system_prompt(self, turns: Sequence[ChatTurn], repository_id: str | None) -> str:
        prompt = SYSTEM_PROMPT
        query = _latest_user_text(turns)
        if self._memory_conn is not None and query != "":
            records = retrieve_records(self._memory_conn, query, None, limit=5)
            if records:
                lines = "\n".join(f"- {item.text[:400]}" for item in records)
                prompt = f"{prompt}\n\nRelevant memories:\n{lines}"
        mentioned = self._mentioned_file_context(query, repository_id)
        if mentioned == "":
            return prompt
        return f"{prompt}\n\nMentioned files:\n{mentioned}"

    def _mentioned_file_context(self, query: str, repository_id: str | None) -> str:
        if not repository_id or self._repos is None or query == "":
            return ""
        blocks: list[str] = []
        for path in mentioned_workspace_paths(query):
            text = self._workspace_file_text(repository_id, path)
            if text is None:
                continue
            blocks.append(f"{path}\n{text}")
        return "\n\n".join(blocks)

    def _workspace_file_text(self, repository_id: str, rel_path: str) -> str | None:
        if self._repos is None:
            return None
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return None
        root = Path(record.realpath).resolve()
        relative = Path(rel_path)
        if relative.is_absolute() or any(part in {"..", ".git"} for part in relative.parts):
            return None
        target = (root / relative).resolve()
        if not _is_inside(root, target) or not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")[:8000]

    def _create_goal(self, repository_id: str, arguments: dict[str, str]) -> str:
        if self._goals is None:
            return "Goals are not available."
        title = arguments.get("title", "").strip()
        criteria = arguments.get("success_criteria", "").strip() or title
        if title == "" or criteria == "":
            return "create_goal needs title and success_criteria."
        goal = self._goals.create(
            GoalSpec(
                repository_id=RepositoryId(repository_id),
                title=title,
                success_criteria=criteria,
                non_goals=arguments.get("non_goals", "").strip()
                or "Out of scope unless you expand the goal.",
                risk_ceiling=arguments.get("risk_ceiling", "low") or "low",
                source=GoalSource.DESKTOP,
                max_attempts=3,
            )
        )
        return f"Created goal {goal.id.value}: {goal.title}"

    def _list_goals(self) -> str:
        if self._goals is None:
            return "Goals are not available."
        items = self._goals.list()
        if not items:
            return "No goals yet."
        return "\n".join(f"{item.id.value} {item.state.value} {item.title}" for item in items[:20])

    def _append(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        tool_name: str | None,
        tool_status: str | None,
    ) -> str:
        now = self._now()
        message_id = f"msg_{uuid4().hex[:16]}"
        self._store.append_message(
            ChatMessageRow(
                id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                tool_name=tool_name,
                tool_status=tool_status,
                created_at=now,
                seq=self._store.next_seq(session_id),
            )
        )
        session = self._store.get_session(session_id)
        self._store.save_session(
            ChatSessionRow(
                id=session.id,
                title=session.title,
                repository_id=session.repository_id,
                created_at=session.created_at,
                updated_at=now,
            )
        )
        return message_id

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.isoformat()
        return datetime.now(tz=UTC).isoformat()


def _session_view(row: ChatSessionRow) -> ChatSessionView:
    return ChatSessionView(
        id=row.id,
        title=row.title,
        repository_id=row.repository_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_view(row: ChatMessageRow) -> ChatMessageView:
    return ChatMessageView(
        id=row.id,
        role=row.role,
        content=row.content,
        tool_name=row.tool_name,
        tool_status=row.tool_status,
        created_at=row.created_at,
    )


def _latest_user_text(turns: Sequence[ChatTurn]) -> str:
    for item in reversed(turns):
        if item.role == "user":
            return item.content
    return ""


def _title_from(message: str, current: str) -> str:
    if current != "New chat":
        return current
    compact = " ".join(message.split())
    if len(compact) <= 48:
        return compact or "New chat"
    return f"{compact[:45]}..."


def _is_inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _stop_partial(reply: str) -> str:
    try:
        if parse_tool_call(reply) is not None:
            return ""
    except ToolParseError:
        return reply
    return reply
