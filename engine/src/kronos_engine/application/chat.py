# SPDX-License-Identifier: AGPL-3.0-or-later
"""Orchestrator chat: agent loop with tools, citations, and draft goals."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from threading import Event, Lock
from typing import Protocol
from uuid import uuid4

from kronos_engine.adapters.models.openai_compatible import (
    CompletionCancelled,
    HttpTransport,
    OpenAICompatibleProvider,
)
from kronos_engine.adapters.secrets.os_store import SecretStoreError
from kronos_engine.application.chat_images import (
    ChatImageInput,
    ChatImagePart,
    append_image_markers,
    decode_chat_images,
    load_chat_image,
    save_chat_image,
    split_user_text_and_image_ids,
    user_message_content_parts,
)
from kronos_engine.application.chat_mentions import mentioned_workspace_paths
from kronos_engine.application.chat_tools import (
    ToolCall,
    ToolParseError,
    parse_tool_call,
    redact_tool_arguments,
)
from kronos_engine.application.chat_workspace_instructions import workspace_instruction_text
from kronos_engine.application.goal_readiness import GoalReadiness, evaluate_goal_readiness
from kronos_engine.application.goals import GoalService
from kronos_engine.application.model_profiles import ModelProfileService, ProviderDraft
from kronos_engine.application.planning import PlanningService
from kronos_engine.application.repositories import RepositoryNotFound, RepositoryService
from kronos_engine.application.safety import evaluate_repository_safety
from kronos_engine.application.workspace_files import (
    list_workspace_files,
    read_workspace_file,
)
from kronos_engine.application.workspace_terminal import run_workspace_command, terminal_run_key
from kronos_engine.application.workspace_writes import (
    WorkspaceWriteTooLarge,
    write_workspace_file,
)
from kronos_engine.domain.entities import EnrolledRepository, EventId, RepositoryId
from kronos_engine.domain.goals import GoalRecord, GoalSource, GoalSpec
from kronos_engine.domain.models import (
    MODEL_ROLES,
    CostCeilingExceeded,
    ModelProfile,
    assert_cost_allowed,
)
from kronos_engine.indexing.context import ContextPack, assemble_context, estimate_tokens
from kronos_engine.memory.procedural import retrieve_records
from kronos_engine.memory.records import MemoryRecord
from kronos_engine.ports.embedding import EmbeddingPort
from kronos_engine.ports.event_store import EventStore
from kronos_engine.ports.forge import GithubAppStatus, GithubConnectionStatus
from kronos_engine.ports.index_store import IndexedChunk
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult
from kronos_engine.ports.model_registry import ModelRegistry, ProviderConfig
from kronos_engine.ports.secrets import ScopedSecret, SecretStore
from kronos_engine.skills.router import route_skills
from kronos_engine.state.conversations import (
    ConversationMessage,
    ConversationRecord,
    SqliteConversationStore,
)
from kronos_engine.state.github_apps import SqliteGithubAppStore
from kronos_engine.state.goals import SqliteGoalStore

MAX_TOOL_ROUNDS = 10
MAX_WRITE_CHARS = 200_000
MAX_RUN_COMMANDS_PER_TURN = 5
COMMAND_TIMEOUT_SECONDS = 60
TOOL_OUTPUT_CLIP = 8_000
MENTION_CLIP = 8_000
DEFAULT_NON_GOALS = "Do not change unrelated files or skip tests."
_SECRET_TTL_SECONDS = 60
STOP_MESSAGE = "Stopped. Ask again when you want to continue."
NO_WORKSPACE = "No workspace is open. Open a git folder first."
FENCE_START = "```tool"
SYSTEM_PROMPT = """You are Kronos, a locally installed coding agent. Answer in plain language.
When you need a tool, emit only a fenced JSON block:

```tool
{"name": "search_index", "query": "onboarding"}
```

Tools: search_index (query), list_files (glob), read_file (path), write_file (path, content),
run_command (command), search_memory (query), create_goal (title, success_criteria),
list_goals, configure_model (provider, display_name, base_url, model, api_key, billed, roles).
configure_model registers a provider and assigns the requested roles. roles is an optional JSON
array of orchestrator, planner, coder, reviewer, and embedding. Always include confirm_replace:
true before changing an existing orchestrator assignment. Never repeat an API key after using it.
Stay inside the current workspace. Do not claim you edited files unless write_file succeeded.
When you show a file in a fenced block, put the path on the fence line, like ts src/app.ts.
run_command runs in the workspace folder. Prefer tests and local tools. Do not push.
Follow workspace instructions when they are provided.
The user may paste screenshots. Use them when they are present.
If you do not need a tool, reply without a tool fence.
/goal hands unattended work to the deterministic system.
You may be shown relevant skill summaries."""

_CANCEL: dict[str, Event] = {}
_CANCEL_LOCK = Lock()


def _cancel_event(conversation_id: str) -> Event:
    with _CANCEL_LOCK:
        return _CANCEL.setdefault(conversation_id, Event())


def request_cancel(conversation_id: str) -> None:
    _cancel_event(conversation_id).set()


class OrchestratorNotConfigured(RuntimeError):
    """Raised when chat cannot call the assigned orchestrator model."""

    def __init__(self) -> None:
        super().__init__(
            "No orchestrator model is configured. Assign a model on the Models page."
        )


@dataclass(frozen=True, slots=True)
class ChatTurn:
    content: str
    citations: tuple[dict[str, object], ...]
    goal_refs: tuple[str, ...]
    model: str | None = None
    token_count: int | None = None


@dataclass(frozen=True, slots=True)
class ToolEvent:
    id: str
    name: str
    status: str
    args: dict[str, object] | None = None
    summary: str | None = None
    output: str | None = None


@dataclass(frozen=True, slots=True)
class GoalEvent:
    id: str
    state: str
    can_execute: bool
    readiness: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ConversationDetail:
    conversation: ConversationRecord
    messages: tuple[ConversationMessage, ...]


class SearchIndexer(Protocol):
    def search(
        self,
        repo_id: str,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 20,
        budget_tokens: int = 4000,
    ) -> ContextPack: ...


CompleteFn = Callable[[CompletionRequest, ScopedSecret | None], CompletionResult]
StreamFn = Callable[[CompletionRequest, ScopedSecret | None], Iterator[str]]
ForgeFor = Callable[[EnrolledRepository], object]


class ChatService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        repos: RepositoryService,
        goals: GoalService,
        planning: PlanningService,
        indexer: SearchIndexer,
        registry: ModelRegistry,
        secrets: SecretStore,
        events: EventStore,
        *,
        complete: CompleteFn | None = None,
        stream: StreamFn | None = None,
        transport: HttpTransport | None = None,
        embeddings: EmbeddingPort | None = None,
        image_root: Path | None = None,
        skills_root: Path | None = None,
        forge_for: ForgeFor | None = None,
    ) -> None:
        self._conn = conn
        self._repos = repos
        self._goals = goals
        self._planning = planning
        self._indexer = indexer
        self._registry = registry
        self._secrets = secrets
        self._events = events
        self._complete = complete
        self._stream = stream
        self._transport = transport
        self._embeddings = embeddings
        self._image_root = image_root
        self._skills_root = skills_root
        self._forge_for = forge_for
        self._store = SqliteConversationStore(conn)
        self._run_commands_this_turn = 0
        self._tool_seq = 0
        self._last_pack = ContextPack(items=())

    def create_conversation(
        self, repository_id: str | None, title: str = "New conversation"
    ) -> ConversationRecord:
        if repository_id is not None:
            self._repos.get(RepositoryId(repository_id))
        label = title.strip() or "New conversation"
        return self._store.create(repository_id, label)

    def list_conversations(self, repository_id: str | None) -> Sequence[ConversationRecord]:
        if repository_id is not None:
            self._repos.get(RepositoryId(repository_id))
        return self._store.list_for_repository(repository_id)

    def list_all_conversations(self) -> Sequence[ConversationRecord]:
        return self._store.list_all()

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        conversation = self._store.get(conversation_id)
        self._sync_progress(conversation_id)
        return ConversationDetail(
            conversation=conversation,
            messages=tuple(self._store.list_messages(conversation_id)),
        )

    def delete_conversation(self, conversation_id: str) -> None:
        self._store.delete(conversation_id)

    def goal_readiness(self, repository_id: str) -> GoalReadiness:
        record = self._repos.get(RepositoryId(repository_id))
        return self._readiness(record)

    def get_chat_image(self, conversation_id: str, image_id: str) -> ChatImageInput:
        self._store.get(conversation_id)
        if self._image_root is None:
            raise LookupError("chat image not found")
        return load_chat_image(self._image_root, conversation_id, image_id)

    def prepare_reply(
        self,
        conversation_id: str,
        content: str,
        *,
        images: Sequence[Mapping[str, str]] | None = None,
    ) -> None:
        self._store.get(conversation_id)
        if _slash_goal_body(content) is not None:
            return
        payloads = tuple(images or ())
        decoded = decode_chat_images(payloads) if payloads else ()
        if content.strip() == "" and not decoded:
            raise ValueError("message is required")
        self._require_orchestrator(cap_tokens=True)

    def handle_message(
        self,
        conversation_id: str,
        content: str,
        *,
        images: Sequence[Mapping[str, str]] | None = None,
    ) -> ChatTurn:
        final: ChatTurn | None = None
        for item in self.stream_message(conversation_id, content, images=images):
            if isinstance(item, ChatTurn):
                final = item
        if final is None:
            raise RuntimeError("chat turn did not complete")
        return final

    def stream_message(
        self,
        conversation_id: str,
        content: str,
        *,
        images: Sequence[Mapping[str, str]] | None = None,
    ) -> Iterator[str | ToolEvent | GoalEvent | ChatTurn]:
        conversation = self._store.get(conversation_id)
        self._sync_progress(conversation_id)
        payloads = tuple(images or ())
        decoded = decode_chat_images(payloads) if payloads else ()
        text = content.strip()
        if text == "" and not decoded:
            raise ValueError("message is required")
        if decoded and self._image_root is None:
            raise ValueError("image storage is not configured")
        refs = (
            tuple(save_chat_image(self._image_root, conversation_id, item) for item in decoded)
            if self._image_root is not None and decoded
            else ()
        )
        stored = append_image_markers(text, refs)
        self._store.add_message(conversation_id, role="user", content=stored)
        slash_body = _slash_goal_body(content)
        if slash_body is not None:
            yield from self._yield_goal_handoff(conversation, *_title_and_criteria(slash_body))
            return
        provider, profile, secret = self._require_orchestrator(cap_tokens=True)
        cancel = _cancel_event(conversation_id)
        cancel.clear()
        self._run_commands_this_turn = 0
        self._tool_seq = 0
        yield from self._run_agent(conversation, profile, provider, secret, cancel)

    def _run_agent(
        self,
        conversation: ConversationRecord,
        profile: ModelProfile,
        provider: ProviderConfig,
        secret: ScopedSecret | None,
        cancel: Event,
    ) -> Iterator[str | ToolEvent | GoalEvent | ChatTurn]:
        window = profile.limits.context_window or 32_000
        budget = min(8000, window // 5)
        for _ in range(MAX_TOOL_ROUNDS):
            if cancel.is_set():
                yield from self._finish_stop(conversation.id, "", None)
                return
            query = _latest_user_text(self._store.list_messages(conversation.id))
            pack = self._context_pack(conversation, query, budget)
            self._last_pack = pack
            system = self._system_prompt(conversation, query, pack)
            history = _trim_history(
                self._store.list_messages(conversation.id),
                window=window,
                budget=budget,
                max_tokens=profile.limits.max_tokens,
                system=system,
            )
            request = CompletionRequest(
                profile=profile,
                prompt=query,
                messages=_completion_messages(history, system, self._image_root),
            )
            try:
                raw, streamed, streaming_id = yield from self._complete_round(
                    conversation.id, provider, request, secret, cancel
                )
            except CompletionCancelled as cancelled:
                yield from self._finish_stop(conversation.id, cancelled.partial, None)
                return
            if cancel.is_set():
                shown = _stop_partial(raw)
                yield from self._finish_stop(conversation.id, shown, streaming_id)
                return
            try:
                call = parse_tool_call(raw)
            except ToolParseError as error:
                turn = self._final_answer(
                    conversation.id,
                    str(error),
                    profile,
                    usage=None,
                    streamed=streamed,
                    streaming_id=streaming_id,
                )
                if turn.content and not streamed:
                    yield turn.content
                yield turn
                return
            if call is not None:
                if streaming_id is not None:
                    self._store.delete_message(streaming_id)
                self._tool_seq += 1
                tool_id = f"t{self._tool_seq}"
                yield ToolEvent(
                    id=tool_id,
                    name=call.name,
                    status="running",
                    args=redact_tool_arguments(call.arguments),
                )
                result, summary, ok = self._execute_tool(call, conversation, cancel)
                clipped = _clip(result, TOOL_OUTPUT_CLIP)
                self._store.add_message(
                    conversation.id,
                    role="tool",
                    content=result,
                    tool_name=call.name,
                    tool_status="ok" if ok else "error",
                    tool_json=json.dumps(
                        {
                            "args": redact_tool_arguments(call.arguments),
                            "summary": summary,
                            "output": clipped,
                        }
                    ),
                )
                yield ToolEvent(
                    id=tool_id,
                    name=call.name,
                    status="ok" if ok else "error",
                    summary=summary,
                    output=clipped,
                )
                continue
            envelope = _parse_envelope(raw)
            if envelope is not None and envelope.get("intent") == "goal":
                if streaming_id is not None:
                    self._store.delete_message(streaming_id)
                title = _string_field(envelope, "title") or _title_and_criteria(query)[0]
                criteria = _string_field(envelope, "success_criteria") or query
                yield from self._yield_goal_handoff(
                    conversation, title, criteria, model=profile.model_id
                )
                return
            answer = raw.strip() or "I had nothing to add."
            if envelope is not None and envelope.get("intent") == "answer":
                extracted = _string_field(envelope, "text") or _string_field(envelope, "content")
                if extracted:
                    answer = extracted
            turn = self._final_answer(
                conversation.id,
                answer,
                profile,
                usage=None,
                streamed=streamed,
                streaming_id=streaming_id,
            )
            if turn.content and not streamed:
                yield turn.content
            yield turn
            return
        turn = ChatTurn(
            content="Stopped after too many tool steps. Ask again with a smaller request.",
            citations=(),
            goal_refs=(),
            model=profile.model_id,
        )
        self._persist_assistant(conversation.id, turn)
        yield turn.content
        yield turn

    def _complete_round(
        self,
        conversation_id: str,
        provider: ProviderConfig,
        request: CompletionRequest,
        secret: ScopedSecret | None,
        cancel: Event,
    ) -> Generator[str, None, tuple[str, bool, str | None]]:
        if self._complete is not None:
            result = self._complete(request, secret)
            return result.text, False, None
        streaming_id: str | None = None

        def on_flush(text: str) -> None:
            nonlocal streaming_id
            streaming_id = self._upsert_stream(conversation_id, streaming_id, text)

        pieces = self._iter_model_tokens(provider, request, secret, cancel)
        raw, streamed = yield from _emit_visible_deltas(pieces, cancel, on_flush=on_flush)
        return raw, streamed, streaming_id

    def _iter_model_tokens(
        self,
        provider: ProviderConfig,
        request: CompletionRequest,
        secret: ScopedSecret | None,
        cancel: Event,
    ) -> Iterator[str]:
        if self._stream is not None:
            yield from self._stream(request, secret)
            return
        adapter = OpenAICompatibleProvider(
            base_url=provider.base_url or "",
            billed=provider.billed,
            transport=self._transport,
        )
        yield from adapter.complete_stream(request, secret, cancel=cancel)

    def _upsert_stream(
        self, conversation_id: str, message_id: str | None, content: str
    ) -> str:
        if message_id is None:
            row = self._store.add_message(
                conversation_id,
                role="assistant",
                content=content,
                tool_status="streaming",
            )
            return row.id
        self._store.update_message(message_id, content=content, tool_status="streaming")
        return message_id

    def _final_answer(
        self,
        conversation_id: str,
        answer: str,
        profile: ModelProfile,
        *,
        usage: int | None,
        streamed: bool,
        streaming_id: str | None,
    ) -> ChatTurn:
        citations = tuple(
            {"path": item.path, "start_line": item.start_line, "end_line": item.end_line}
            for item in self._last_pack.items
            if not item.path.startswith("memory/")
        )
        turn = ChatTurn(
            content=answer,
            citations=citations,
            goal_refs=(),
            model=profile.model_id,
            token_count=usage,
        )
        if streaming_id is not None:
            self._store.update_message(
                streaming_id,
                content=turn.content,
                tool_status=None,
                citations=turn.citations,
                goal_refs=turn.goal_refs,
                model=turn.model,
                token_count=turn.token_count,
            )
        else:
            self._persist_assistant(conversation_id, turn)
        _ = streamed
        return turn

    def _finish_stop(
        self, conversation_id: str, partial: str, message_id: str | None
    ) -> Iterator[str | ChatTurn]:
        body = STOP_MESSAGE if partial.strip() == "" else f"{partial.rstrip()}\n\n{STOP_MESSAGE}"
        turn = ChatTurn(content=body, citations=(), goal_refs=())
        if message_id is not None:
            self._store.update_message(message_id, content=body, tool_status=None)
        else:
            self._persist_assistant(conversation_id, turn)
        yield turn

    def _yield_goal_handoff(
        self,
        conversation: ConversationRecord,
        title: str,
        success_criteria: str,
        *,
        model: str | None = None,
    ) -> Iterator[str | GoalEvent | ChatTurn]:
        if conversation.repository_id is None:
            turn = ChatTurn(content=NO_WORKSPACE, citations=(), goal_refs=(), model=model)
            if turn.content:
                yield turn.content
            self._persist_assistant(conversation.id, turn)
            yield turn
            return
        turn, event = self._create_goal_turn(conversation, title, success_criteria)
        turn = replace(turn, model=model)
        yield event
        if turn.content:
            yield turn.content
        self._persist_assistant(conversation.id, turn)
        yield turn

    def _create_goal_turn(
        self, conversation: ConversationRecord, title: str, success_criteria: str
    ) -> tuple[ChatTurn, GoalEvent]:
        repo = self._repos.get(RepositoryId(conversation.repository_id or ""))
        goal = self._goals.create(
            GoalSpec(
                repository_id=repo.id,
                title=title,
                success_criteria=success_criteria,
                non_goals=DEFAULT_NON_GOALS,
                risk_ceiling="low",
                source=GoalSource.CHAT,
                max_attempts=repo.policy.budgets.max_attempts_per_issue,
            )
        )
        plan_error: str | None = None
        try:
            self._planning.plan(goal.id)
        except Exception as error:  # noqa: BLE001 — leave draft on any planner failure
            plan_error = str(error)
        goal = self._goals.get(goal.id)
        readiness = self._readiness(repo)
        content = _goal_reply_markdown(goal, readiness, plan_error)
        turn = ChatTurn(content=content, citations=(), goal_refs=(goal.id.value,))
        event = GoalEvent(
            id=goal.id.value,
            state=goal.state.value,
            can_execute=readiness.can_execute,
            readiness=tuple(
                {
                    "id": item.id,
                    "label": item.label,
                    "ok": item.ok,
                    "detail": item.detail,
                }
                for item in readiness.checks
            ),
        )
        return turn, event

    def _readiness(self, repo: EnrolledRepository) -> GoalReadiness:
        record = repo
        assignments = self._registry.load_assignments()
        apps = SqliteGithubAppStore(self._conn)
        github_status = GithubConnectionStatus(
            controller=_github_app_status(apps.get("controller")),
            reviewer=_github_app_status(apps.get("reviewer")),
            webhook_enabled=False,
            poll_mode="conditional",
            github_cli_present=False,
        )
        forge: object | None = None
        if self._forge_for is not None:
            try:
                forge = self._forge_for(record)
            except Exception:  # noqa: BLE001 — fail closed
                forge = None
        safety = evaluate_repository_safety(record, forge=forge, reviewer=apps.get("reviewer"))
        meter = SqliteGoalStore(self._conn).budget_meter(record.id, date.today().isoformat())
        return evaluate_goal_readiness(
            record,
            assignments=assignments,
            safety=safety,
            github_status=github_status,
            meter=meter,
        )

    def _persist_assistant(self, conversation_id: str, turn: ChatTurn) -> None:
        self._store.add_message(
            conversation_id,
            role="assistant",
            content=turn.content,
            citations=turn.citations,
            goal_refs=turn.goal_refs,
            model=turn.model,
            token_count=turn.token_count,
        )

    def _sync_progress(self, conversation_id: str) -> None:
        messages = self._store.list_messages(conversation_id)
        linked: set[str] = set()
        seen = {item.id for item in messages}
        for item in messages:
            linked.update(item.goal_refs)
        if not linked:
            return
        for event in self._events.list_after(0):
            if not (event.type.startswith("goal.") or event.type.startswith("task.")):
                continue
            goal_id = event.payload.get("goal_id")
            if not isinstance(goal_id, str) or goal_id not in linked:
                continue
            message_id = f"sys_{event.id.value}"
            if message_id in seen:
                continue
            payload = json.dumps(dict(event.payload), sort_keys=True)
            self._store.add_message(
                conversation_id,
                role="system",
                content=f"{event.type} {payload}",
                message_id=message_id,
            )
            seen.add(message_id)

    def _require_orchestrator(
        self, *, cap_tokens: bool
    ) -> tuple[ProviderConfig, ModelProfile, ScopedSecret | None]:
        assignments = self._registry.load_assignments()
        profile_id = assignments.orchestrator
        if not profile_id:
            raise OrchestratorNotConfigured()
        profiles = {item.id: item for item in self._registry.list_profiles()}
        profile = profiles.get(profile_id)
        if profile is None:
            raise OrchestratorNotConfigured()
        providers = {item.id: item for item in self._registry.list_providers()}
        provider = providers.get(profile.provider_id)
        if provider is None or not provider.base_url:
            raise OrchestratorNotConfigured()
        try:
            raw = self._secrets.get(provider.secret_ref)
        except SecretStoreError as error:
            if provider.billed or profile.billed:
                raise OrchestratorNotConfigured() from error
            raw = None
        if not raw and provider.billed:
            raise OrchestratorNotConfigured()
        secret = ScopedSecret(value=raw, ttl_seconds=_SECRET_TTL_SECONDS) if raw else None
        billed = provider.billed or profile.billed
        try:
            assert_cost_allowed(profile.limits, estimated_cost=0.0, billed=billed)
        except CostCeilingExceeded as error:
            raise OrchestratorNotConfigured() from error
        _ = cap_tokens
        return provider, profile, secret

    def _context_pack(
        self, conversation: ConversationRecord, query: str, budget: int
    ) -> ContextPack:
        if not conversation.repository_id or query.strip() == "":
            pack = ContextPack(items=())
        else:
            pack = self._indexer.search(
                conversation.repository_id,
                query,
                mode="hybrid",
                budget_tokens=budget,
            )
        memories = retrieve_records(self._conn, query, self._embeddings)
        return _merge_memory(pack, memories, budget)

    def _system_prompt(
        self, conversation: ConversationRecord, query: str, pack: ContextPack
    ) -> str:
        context_blocks = [
            f"{item.path}:{item.start_line}-{item.end_line}\n{item.text}" for item in pack.items
        ]
        context = "\n\n".join(context_blocks) if context_blocks else "(no retrieved context)"
        prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context}"
        instructions = self._workspace_instructions(conversation.repository_id)
        if instructions != "":
            prompt = f"{prompt}\n\nWorkspace instructions:\n{instructions}"
        if query != "":
            records = retrieve_records(self._conn, query, self._embeddings, limit=5)
            if records:
                lines = "\n".join(f"- {item.text[:400]}" for item in records)
                prompt = f"{prompt}\n\nRelevant memories:\n{lines}"
        mentioned = self._mentioned_file_context(query, conversation.repository_id)
        if mentioned != "":
            prompt = f"{prompt}\n\nMentioned files:\n{mentioned}"
        skills = self._skill_summaries(query)
        if skills != "":
            prompt = f"{prompt}\n\n{skills}"
        return prompt

    def _workspace_instructions(self, repository_id: str | None) -> str:
        if not repository_id:
            return ""
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return ""
        return workspace_instruction_text(Path(record.realpath))

    def _mentioned_file_context(self, query: str, repository_id: str | None) -> str:
        if not repository_id or query == "":
            return ""
        blocks: list[str] = []
        for path in mentioned_workspace_paths(query):
            text = self._workspace_file_text(repository_id, path)
            if text is None:
                continue
            blocks.append(f"{path}\n{text}")
        return "\n\n".join(blocks)

    def _workspace_file_text(self, repository_id: str, rel_path: str) -> str | None:
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return None
        try:
            payload = read_workspace_file(Path(record.realpath), rel_path)
        except ValueError:
            return None
        if payload["binary"]:
            return None
        return payload["content"][:MENTION_CLIP]

    def _skill_summaries(self, query: str) -> str:
        if self._skills_root is None or query.strip() == "":
            return ""
        try:
            from kronos_engine.skills.catalog import SkillCatalog

            catalog = SkillCatalog(
                self._conn,
                skills_root=self._skills_root,
                store_dir=self._skills_root / "_installed",
            )
            routed = route_skills(query, catalog.list(), budget_tokens=400)
        except Exception:  # noqa: BLE001 — skills are optional in chat
            return ""
        summaries = routed.summaries[:3]
        if not summaries:
            return ""
        lines = "\n".join(f"- {item.name}: {item.description}" for item in summaries)
        return f"Relevant skill summaries:\n{lines}"

    def _execute_tool(
        self, call: ToolCall, conversation: ConversationRecord, cancel: Event
    ) -> tuple[str, str, bool]:
        try:
            result = self._run_tool(call, conversation, cancel)
            summary = _tool_summary(call.name, result)
            return result, summary, True
        except Exception as error:  # noqa: BLE001 — tool errors stay in the thread
            text = _redact_tool_text(str(error), call.arguments)
            return text, text, False

    def _run_tool(
        self, call: ToolCall, conversation: ConversationRecord, cancel: Event
    ) -> str:
        if call.name == "list_goals":
            return self._list_goals()
        if call.name == "search_memory":
            return self._search_memory(_tool_string(call.arguments, "query"))
        if call.name == "configure_model":
            return self._configure_model(call.arguments)
        repo_id = conversation.repository_id
        if repo_id is None or repo_id == "":
            return NO_WORKSPACE
        if call.name == "search_index":
            return self._search_index(repo_id, _tool_string(call.arguments, "query"))
        if call.name == "list_files":
            return self._list_files(repo_id, _tool_string(call.arguments, "glob"))
        if call.name == "read_file":
            return self._read_file(repo_id, _tool_string(call.arguments, "path"))
        if call.name == "write_file":
            return self._write_file(
                repo_id,
                _tool_string(call.arguments, "path"),
                _tool_string(call.arguments, "content"),
            )
        if call.name == "run_command":
            return self._run_command(repo_id, _tool_string(call.arguments, "command"), cancel)
        if call.name == "create_goal":
            return self._create_goal(repo_id, call.arguments)
        return "unknown tool"

    def _configure_model(self, arguments: dict[str, object]) -> str:
        kind = _tool_string(arguments, "provider") or _tool_string(arguments, "kind")
        model_id = _tool_string(arguments, "model") or _tool_string(arguments, "model_id")
        if kind == "" or model_id == "":
            return "configure_model needs provider and model."
        roles = _model_roles(arguments.get("roles"))
        service = ModelProfileService(self._registry, self._secrets)
        current = service.assignments().as_dict()
        replaces_orchestrator = (
            "orchestrator" in roles and current["orchestrator"] is not None
        )
        if replaces_orchestrator and not _tool_bool(arguments.get("confirm_replace")):
            return (
                "An orchestrator is already assigned. Confirm replacement by rerunning "
                "configure_model with confirm_replace: true."
            )
        provider = service.register_provider(
            ProviderDraft(
                kind=kind,
                display_name=_tool_string(arguments, "display_name") or kind,
                base_url=_tool_optional_string(arguments, "base_url"),
                billed=_tool_bool(arguments.get("billed")),
                api_key=_tool_optional_string(arguments, "api_key"),
                model_id=model_id,
            )
        )
        profiles = {
            profile.role: profile.id
            for profile in service.list_profiles()
            if profile.provider_id == provider.id
        }
        next_assignments = dict(current)
        for role in MODEL_ROLES:
            if role in roles or next_assignments[role] is None:
                next_assignments[role] = profiles[role]
        service.assign({role: next_assignments[role] or "" for role in MODEL_ROLES})
        changed = [role for role in MODEL_ROLES if next_assignments[role] != current[role]]
        detail = (
            " Replaced existing model assignments for: " + ", ".join(changed) + "."
            if changed
            else ""
        )
        return (
            f"Configured {provider.display_name} with model {model_id}. "
            f"Assigned roles: {', '.join(roles)}.{detail}"
        )

    def _search_index(self, repository_id: str, query: str) -> str:
        pack = self._indexer.search(repository_id, query)
        if not pack.items:
            return "No index hits. Rebuild the index after opening a workspace."
        lines = [
            f"{item.path}:{item.start_line}-{item.end_line} {item.text[:240]}"
            for item in pack.items[:8]
        ]
        return _clip("\n".join(lines), TOOL_OUTPUT_CLIP)

    def _list_files(self, repository_id: str, glob: str) -> str:
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return "Workspace was not found."
        pattern = glob.strip()
        paths: list[str] = []
        for entry in list_workspace_files(Path(record.realpath)):
            path = entry["path"]
            if pattern and not _glob_matches(path, pattern):
                continue
            paths.append(path)
        if not paths:
            return "No matching files."
        return _clip("\n".join(paths), TOOL_OUTPUT_CLIP)

    def _read_file(self, repository_id: str, rel_path: str) -> str:
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return "Workspace was not found."
        try:
            payload = read_workspace_file(Path(record.realpath), rel_path)
        except ValueError as error:
            return str(error)
        if payload["binary"]:
            return "That file is binary."
        return _clip(payload["content"], TOOL_OUTPUT_CLIP)

    def _write_file(self, repository_id: str, rel_path: str, content: str) -> str:
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return "Workspace was not found."
        if len(content) > MAX_WRITE_CHARS:
            return (
                f"File is too large to write here. Keep it under {MAX_WRITE_CHARS} characters."
            )
        try:
            written = write_workspace_file(
                Path(record.realpath),
                repository_id,
                rel_path,
                content,
                backups=self._store,
                locked_prefixes=record.policy.paths.locked_prefixes,
                now=datetime.now(tz=UTC).isoformat(),
            )
        except WorkspaceWriteTooLarge as error:
            return str(error)
        except ValueError as error:
            return str(error)
        try:
            self._events.append(
                EventId(f"evt_{uuid4().hex[:16]}"),
                "git.wrote",
                {
                    "repository_id": repository_id,
                    "path": written.path,
                    "summary": written.summary,
                    "patch": written.patch,
                },
            )
            self._conn.commit()
        except Exception:
            pass
        return f"Wrote {written.path} ({len(content)} characters)."

    def _run_command(self, repository_id: str, command: str, cancel: Event) -> str:
        if self._run_commands_this_turn >= MAX_RUN_COMMANDS_PER_TURN:
            return (
                f"This turn already ran {MAX_RUN_COMMANDS_PER_TURN} commands. "
                "Ask again if you need another."
            )
        stripped = command.strip()
        if stripped == "":
            return "A command is required."
        try:
            record = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return "Workspace was not found."
        self._run_commands_this_turn += 1
        result = run_workspace_command(
            Path(record.realpath),
            stripped,
            timeout_seconds=COMMAND_TIMEOUT_SECONDS,
            run_key=terminal_run_key(repository_id),
            should_stop=cancel.is_set,
        )
        if result["cancelled"]:
            header = "Stopped."
        elif result["timed_out"]:
            header = "The command timed out."
        elif result["exit_code"] is None:
            header = "Finished."
        else:
            header = f"Exit {result['exit_code']}"
        output = result["output"].strip()
        if output == "":
            return header
        return _clip(f"{header}\n\n{output}", TOOL_OUTPUT_CLIP)

    def _search_memory(self, query: str) -> str:
        records = retrieve_records(self._conn, query, self._embeddings, limit=5)
        if not records:
            return "No matching memories."
        return "\n".join(item.text[:400] for item in records)

    def _create_goal(self, repository_id: str, arguments: dict[str, str]) -> str:
        title = arguments.get("title", "").strip()
        criteria = arguments.get("success_criteria", "").strip() or title
        if title == "" or criteria == "":
            return "create_goal needs title and success_criteria."
        try:
            repo = self._repos.get(RepositoryId(repository_id))
        except (RepositoryNotFound, LookupError, ValueError):
            return "Workspace was not found."
        goal = self._goals.create(
            GoalSpec(
                repository_id=repo.id,
                title=title,
                success_criteria=criteria,
                non_goals=arguments.get("non_goals", "").strip() or DEFAULT_NON_GOALS,
                risk_ceiling=arguments.get("risk_ceiling", "low") or "low",
                source=GoalSource.CHAT,
                max_attempts=repo.policy.budgets.max_attempts_per_issue,
            )
        )
        return f"Created goal {goal.id.value}: {goal.title}"

    def _list_goals(self) -> str:
        items = self._goals.list()
        if not items:
            return "No goals yet."
        return "\n".join(f"{item.id.value} {item.state.value} {item.title}" for item in items[:20])


def _emit_visible_deltas(
    pieces: Iterator[str],
    cancel: Event,
    *,
    on_flush: Callable[[str], None],
) -> Generator[str, None, tuple[str, bool]]:
    parts: list[str] = []
    emitted = 0
    streamed = False
    for piece in pieces:
        if cancel.is_set():
            break
        parts.append(piece)
        raw = "".join(parts)
        flushable = _flushable_prefix(raw)
        if len(flushable) > emitted:
            chunk = flushable[emitted:]
            emitted = len(flushable)
            on_flush(flushable)
            if chunk:
                yield chunk
                streamed = True
    return "".join(parts), streamed


def _flushable_prefix(buffer: str) -> str:
    stripped = buffer.lstrip()
    if not stripped:
        return ""
    if stripped.startswith("{"):
        return ""
    if FENCE_START.startswith(stripped):
        return ""
    from kronos_engine.application.chat_tools import TOOL_FENCE

    match = TOOL_FENCE.search(buffer)
    if match is not None:
        return buffer[: match.start()]
    for n in range(len(FENCE_START), 0, -1):
        if buffer.endswith(FENCE_START[:n]):
            return buffer[:-n]
    return buffer


def _trim_history(
    messages: Sequence[ConversationMessage],
    *,
    window: int,
    budget: int,
    max_tokens: int,
    system: str,
) -> tuple[ConversationMessage, ...]:
    room = window - budget - (max_tokens or 4096) - _char_tokens(system)
    selected: list[ConversationMessage] = []
    used = 0
    for item in reversed(messages):
        cost = _char_tokens(item.content)
        if selected and used + cost > max(0, room):
            break
        selected.append(item)
        used += cost
    selected.reverse()
    return tuple(selected)


def _char_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def _completion_messages(
    history: Sequence[ConversationMessage],
    system: str,
    image_root: Path | None,
) -> tuple[dict[str, object], ...]:
    messages: list[dict[str, object]] = [{"role": "system", "content": system}]
    for item in history:
        if item.role == "user":
            messages.append(_user_message(item, image_root))
        elif item.role == "tool":
            name = item.tool_name or "tool"
            messages.append(
                {"role": "user", "content": f"Tool {name} result:\n{item.content}"}
            )
        else:
            messages.append({"role": item.role, "content": item.content})
    return tuple(messages)


def _user_message(item: ConversationMessage, image_root: Path | None) -> dict[str, object]:
    text, image_ids = split_user_text_and_image_ids(item.content)
    if not image_ids:
        return {"role": "user", "content": item.content}
    parts: list[ChatImagePart] = []
    if image_root is not None:
        for image_id in image_ids:
            try:
                loaded = load_chat_image(image_root, item.conversation_id, image_id)
            except LookupError:
                continue
            parts.append(ChatImagePart(mime=loaded.mime, data=loaded.data))
    if not parts:
        return {"role": "user", "content": text or item.content}
    return {"role": "user", "content": user_message_content_parts(text, parts)}


def _slash_goal_body(text: str) -> str | None:
    if not text.startswith("/goal"):
        return None
    rest = text[5:]
    if rest == "" or rest[0].isspace():
        return rest.lstrip()
    return None


def _title_and_criteria(text: str) -> tuple[str, str]:
    body = text.strip() or "Chat goal"
    lines = body.splitlines()
    title = lines[0].strip() or "Chat goal"
    remainder = "\n".join(lines[1:]).strip()
    criteria = remainder if remainder else body
    return title, criteria


def _parse_envelope(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed: object = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get("intent") not in {"answer", "goal"}:
        return None
    return parsed


def _string_field(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _merge_memory(
    pack: ContextPack, memories: Sequence[MemoryRecord], budget: int
) -> ContextPack:
    used = sum(estimate_tokens(item.text) for item in pack.items) if pack.items else 0
    remaining = budget - used
    if remaining <= 0 or not memories:
        return pack
    chunks: list[tuple[IndexedChunk, tuple[str, ...]]] = []
    for record in memories:
        chunks.append(
            (
                IndexedChunk(
                    chunk_id=record.id,
                    path=f"memory/{record.id}",
                    start_line=1,
                    end_line=1,
                    symbol=None,
                    kind="memory",
                    language="",
                    commit="",
                    content_hash=record.source_sha,
                    text=record.text,
                    trust="memory",
                ),
                ("memory",),
            )
        )
    extra = assemble_context(chunks, budget_tokens=remaining)
    return ContextPack(items=pack.items + extra.items)


def _latest_user_text(messages: Sequence[ConversationMessage]) -> str:
    for item in reversed(messages):
        if item.role == "user":
            text, _ids = split_user_text_and_image_ids(item.content)
            return text
    return ""


def _stop_partial(reply: str) -> str:
    try:
        if parse_tool_call(reply) is not None:
            return ""
    except ToolParseError:
        return reply
    return _flushable_prefix(reply) or reply


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _tool_summary(name: str, result: str) -> str:
    first = result.strip().splitlines()[0] if result.strip() else name
    return first[:240]


def _tool_string(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _tool_optional_string(arguments: Mapping[str, object], key: str) -> str | None:
    value = _tool_string(arguments, key).strip()
    return value or None


def _tool_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.casefold() in {"1", "true", "yes"}


def _model_roles(value: object) -> tuple[str, ...]:
    if value is None:
        return MODEL_ROLES
    if isinstance(value, str):
        requested = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        requested = [item.strip() for item in value if item.strip()]
    else:
        raise ValueError("roles must be a JSON array of model role names")
    unknown = sorted(set(requested) - set(MODEL_ROLES))
    if unknown:
        raise ValueError(f"unknown roles: {', '.join(unknown)}")
    if not requested:
        raise ValueError("at least one role is required")
    return tuple(role for role in MODEL_ROLES if role in requested)


def _redact_tool_text(text: str, arguments: Mapping[str, object]) -> str:
    api_key = arguments.get("api_key")
    if isinstance(api_key, str) and api_key:
        return text.replace(api_key, "[REDACTED]")
    return text


def _glob_matches(path: str, pattern: str) -> bool:
    from fnmatch import fnmatch

    posix = PurePosixPath(path)
    try:
        if posix.match(pattern):
            return True
    except ValueError:
        pass
    return fnmatch(path, pattern) or fnmatch(posix.name, pattern)


def _github_app_status(record: object) -> GithubAppStatus:
    if record is None:
        return GithubAppStatus(registered=False, installed=False, verified=False)
    installation_id = getattr(record, "installation_id", None)
    verified_at = getattr(record, "verified_at", None)
    return GithubAppStatus(
        registered=True,
        installed=installation_id is not None,
        verified=verified_at is not None,
        app_id=getattr(record, "app_id", None),
        slug=getattr(record, "slug", None),
    )


def _goal_reply_markdown(
    goal: GoalRecord, readiness: GoalReadiness, plan_error: str | None
) -> str:
    lines = [f"Draft goal `{goal.id.value}` created."]
    if plan_error:
        lines.append(f"Planning failed: {plan_error}. The goal remains in draft.")
    for check in readiness.checks:
        lines.append(f"{check.label}: {check.detail}")
    if readiness.can_execute:
        lines.append("This goal can execute now.")
    else:
        lines.append("This goal cannot execute unattended yet.")
    return "\n".join(lines)
