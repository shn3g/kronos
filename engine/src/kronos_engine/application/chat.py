# SPDX-License-Identifier: AGPL-3.0-or-later
"""Orchestrator chat: cheap answers with citations, draft goals for real work."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Generator, Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from kronos_engine.adapters.models.openai_compatible import HttpTransport, OpenAICompatibleProvider
from kronos_engine.adapters.secrets.os_store import SecretStoreError
from kronos_engine.application.goals import GoalService
from kronos_engine.application.planning import PlanningService
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.domain.entities import RepositoryId
from kronos_engine.domain.goals import GoalSource, GoalSpec
from kronos_engine.domain.models import CostCeilingExceeded, ModelProfile, assert_cost_allowed
from kronos_engine.indexing.context import ContextPack, assemble_context, estimate_tokens
from kronos_engine.memory.procedural import retrieve_records
from kronos_engine.memory.records import MemoryRecord
from kronos_engine.ports.embedding import EmbeddingPort
from kronos_engine.ports.event_store import EventStore
from kronos_engine.ports.index_store import IndexedChunk
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult
from kronos_engine.ports.model_registry import ModelRegistry, ProviderConfig
from kronos_engine.ports.secrets import ScopedSecret, SecretStore
from kronos_engine.state.conversations import (
    ConversationMessage,
    ConversationRecord,
    SqliteConversationStore,
)

ANSWER_TOKEN_CAP = 1024
CONTEXT_BUDGET_TOKENS = 2000
DEFAULT_NON_GOALS = "Do not change unrelated files or skip tests."
_SECRET_TTL_SECONDS = 60
_SYSTEM_PROMPT = (
    "You are the Kronos orchestrator. Answer questions about this repository using the "
    "packed context. If the user is requesting implementation or other real work, return "
    'ONLY JSON {"intent":"goal","title":"...","success_criteria":"..."}. Otherwise answer '
    "in plain language. Never edit files, never call GitHub, and never invent tools."
)


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
        self._store = SqliteConversationStore(conn)

    def create_conversation(
        self, repository_id: str, title: str = "New conversation"
    ) -> ConversationRecord:
        self._repos.get(RepositoryId(repository_id))
        label = title.strip() or "New conversation"
        return self._store.create(repository_id, label)

    def list_conversations(self, repository_id: str) -> Sequence[ConversationRecord]:
        self._repos.get(RepositoryId(repository_id))
        return self._store.list_for_repository(repository_id)

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        conversation = self._store.get(conversation_id)
        self._sync_progress(conversation_id)
        return ConversationDetail(
            conversation=conversation,
            messages=tuple(self._store.list_messages(conversation_id)),
        )

    def delete_conversation(self, conversation_id: str) -> None:
        self._store.delete(conversation_id)

    def prepare_reply(self, conversation_id: str, content: str) -> None:
        self._store.get(conversation_id)
        if _slash_goal_body(content) is not None:
            return
        self._require_orchestrator(cap_tokens=True)

    def handle_message(self, conversation_id: str, content: str) -> ChatTurn:
        final: ChatTurn | None = None
        for item in self.stream_message(conversation_id, content):
            if isinstance(item, ChatTurn):
                final = item
        if final is None:
            raise RuntimeError("chat turn did not complete")
        return final

    def stream_message(self, conversation_id: str, content: str) -> Iterator[str | ChatTurn]:
        conversation = self._store.get(conversation_id)
        self._sync_progress(conversation_id)
        history = [
            item
            for item in self._store.list_messages(conversation_id)
            if item.role in {"user", "assistant", "system"}
        ]
        self._store.add_message(conversation_id, role="user", content=content)
        slash_body = _slash_goal_body(content)
        if slash_body is not None:
            turn = self._create_goal_turn(conversation, *_title_and_criteria(slash_body))
            if turn.content:
                yield turn.content
            self._persist_assistant(conversation_id, turn)
            yield turn
            return
        provider, profile, secret = self._require_orchestrator(cap_tokens=True)
        pack = self._indexer.search(
            _repository_id(conversation),
            content,
            mode="hybrid",
            budget_tokens=CONTEXT_BUDGET_TOKENS,
        )
        memories = retrieve_records(self._conn, content, self._embeddings)
        packed = _merge_memory(pack, memories)
        request = CompletionRequest(
            profile=profile,
            prompt=content,
            messages=_completion_messages(history, content, packed),
        )
        usage: int | None = None
        streamed = False
        if self._complete is not None:
            result = self._complete(request, secret)
            usage = result.usage.tokens
            raw = result.text
        else:
            raw, streamed = yield from _emit_plain_deltas(
                self._iter_model_tokens(provider, request, secret)
            )
        envelope = _parse_envelope(raw)
        if envelope is not None and envelope.get("intent") == "goal":
            title = _string_field(envelope, "title") or _title_and_criteria(content)[0]
            criteria = _string_field(envelope, "success_criteria") or content
            turn = self._create_goal_turn(conversation, title, criteria)
            turn = replace(turn, model=profile.model_id, token_count=usage)
            if turn.content:
                yield turn.content
            self._persist_assistant(conversation_id, turn)
            yield turn
            return
        answer = raw
        if envelope is not None and envelope.get("intent") == "answer":
            extracted = _string_field(envelope, "text") or _string_field(envelope, "content")
            if extracted:
                answer = extracted
        citations = tuple(
            {"path": item.path, "start_line": item.start_line, "end_line": item.end_line}
            for item in packed.items
            if not item.path.startswith("memory/")
        )
        turn = ChatTurn(
            content=answer,
            citations=citations,
            goal_refs=(),
            model=profile.model_id,
            token_count=usage,
        )
        if answer and not streamed:
            yield answer
        self._persist_assistant(conversation_id, turn)
        yield turn

    def _iter_model_tokens(
        self,
        provider: ProviderConfig,
        request: CompletionRequest,
        secret: ScopedSecret | None,
    ) -> Iterator[str]:
        if self._stream is not None:
            yield from self._stream(request, secret)
            return
        adapter = OpenAICompatibleProvider(
            base_url=provider.base_url or "",
            billed=provider.billed,
            transport=self._transport,
        )
        yield from adapter.stream(request, secret)

    def _create_goal_turn(
        self, conversation: ConversationRecord, title: str, success_criteria: str
    ) -> ChatTurn:
        repo = self._repos.get(RepositoryId(_repository_id(conversation)))
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
        content = f"Created draft goal '{goal.title}' ({goal.id.value})."
        if plan_error:
            content += f" Planning failed: {plan_error}. The goal remains in draft."
        else:
            content += " Planned successfully."
        return ChatTurn(content=content, citations=(), goal_refs=(goal.id.value,))

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
            raise OrchestratorNotConfigured() from error
        if not raw and provider.billed:
            raise OrchestratorNotConfigured()
        secret = ScopedSecret(value=raw, ttl_seconds=_SECRET_TTL_SECONDS) if raw else None
        billed = provider.billed or profile.billed
        try:
            assert_cost_allowed(profile.limits, estimated_cost=0.0, billed=billed)
        except CostCeilingExceeded as error:
            raise OrchestratorNotConfigured() from error
        if cap_tokens:
            capped = min(ANSWER_TOKEN_CAP, profile.limits.max_tokens)
            profile = replace(profile, limits=replace(profile.limits, max_tokens=capped))
        return provider, profile, secret


def _emit_plain_deltas(
    pieces: Iterator[str],
) -> Generator[str, None, tuple[str, bool]]:
    parts: list[str] = []
    json_mode: bool | None = None
    streamed = False
    for piece in pieces:
        parts.append(piece)
        if json_mode is True:
            continue
        if json_mode is False:
            if piece:
                yield piece
                streamed = True
            continue
        stripped = "".join(parts).lstrip()
        if not stripped:
            continue
        if stripped.startswith("{"):
            json_mode = True
            continue
        json_mode = False
        for part in parts:
            if part:
                yield part
                streamed = True
    return "".join(parts), streamed


def _repository_id(conversation: ConversationRecord) -> str:
    if conversation.repository_id is None:
        raise LookupError(f"conversation has no workspace: {conversation.id}")
    return conversation.repository_id


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


def _merge_memory(pack: ContextPack, memories: Sequence[MemoryRecord]) -> ContextPack:
    used = sum(estimate_tokens(item.text) for item in pack.items) if pack.items else 0
    remaining = CONTEXT_BUDGET_TOKENS - used
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


def _completion_messages(
    history: Sequence[ConversationMessage],
    user_text: str,
    pack: ContextPack,
) -> tuple[dict[str, str], ...]:
    context_blocks = [
        f"{item.path}:{item.start_line}-{item.end_line}\n{item.text}" for item in pack.items
    ]
    context = "\n\n".join(context_blocks) if context_blocks else "(no retrieved context)"
    messages: list[dict[str, str]] = [
        {"role": "system", "content": f"{_SYSTEM_PROMPT}\n\nContext:\n{context}"}
    ]
    for item in history:
        messages.append({"role": item.role, "content": item.content})
    messages.append({"role": "user", "content": user_text})
    return tuple(messages)
