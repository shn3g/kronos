# SPDX-License-Identifier: AGPL-3.0-or-later
"""ChatService routes /goal to draft goals and answers with citations. No GitHub."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.adapters.secrets.os_store import SecretStoreError
from kronos_engine.application.chat import (
    ChatService,
    ChatTurn,
    GoalEvent,
    OrchestratorNotConfigured,
    ToolEvent,
    request_cancel,
)
from kronos_engine.application.goals import GoalService
from kronos_engine.application.model_profiles import ModelProfileService, ProviderDraft
from kronos_engine.application.planning import PlanningService
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.paths import resolve_paths
from kronos_engine.domain.goals import GoalSource, GoalState
from kronos_engine.domain.models import MODEL_ROLES, ModelProfile, ResourceLimits
from kronos_engine.domain.tasks import SchemaError
from kronos_engine.indexing.context import ContextItem, ContextPack
from kronos_engine.memory.procedural import persist_record
from kronos_engine.memory.records import MemoryKind, MemoryRecord, MemoryStatus
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult, TokenUsage
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.model_profiles import SqliteModelRegistry
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@dataclass
class _Indexer:
    pack: ContextPack
    calls: list[dict[str, object]]

    def search(
        self,
        repo_id: str,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 20,
        budget_tokens: int = 4000,
    ) -> ContextPack:
        self.calls.append(
            {
                "repo_id": repo_id,
                "query": query,
                "mode": mode,
                "limit": limit,
                "budget_tokens": budget_tokens,
            }
        )
        return self.pack


class _BoomPlanner:
    def plan(self, goal: object) -> dict[str, object]:
        _ = goal
        raise SchemaError("planner exploded")


class _OkPlanner:
    def plan(self, goal: object) -> dict[str, object]:
        _ = goal
        return {
            "tasks": [
                {
                    "id": "task_from_chat",
                    "title": "from chat",
                    "kind": "implementation",
                    "depends_on": [],
                    "evidence": [{"path": "src/math.py", "line": 1}],
                    "size": "S",
                    "baseline_size": "S",
                    "risk": "low",
                    "scope_paths": ["src/math.py"],
                }
            ]
        }


def _paths(tmp_path: Path):
    return resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )


def _pack() -> ContextPack:
    return ContextPack(
        items=(
            ContextItem(
                path="src/math.py",
                start_line=3,
                end_line=12,
                commit="abc",
                text="def add(a, b):\n    return a + b\n",
                symbol="add",
                rank_sources=("sparse", "dense"),
                trust="high",
            ),
        )
    )


def _harness(
    tmp_path: Path,
    *,
    planner: object | None = None,
    complete: object | None = None,
    stream: object | None = None,
    assign_orchestrator: bool = True,
    profile_max_tokens: int = 4096,
    context_window: int = 32_000,
    policy_overrides: dict[str, object] | None = None,
    billed: bool = False,
    api_key: str | None = "sk-chat",
    cost_ceiling: float = 0.0,
    secrets: InMemorySecretStore | None = None,
    image_root: Path | None = None,
):
    paths = _paths(tmp_path)
    database = Database(paths.database)
    conn = database.connect()
    secrets = secrets if secrets is not None else InMemorySecretStore()
    registry = SqliteModelRegistry(conn)
    models = ModelProfileService(registry, secrets)
    repos = RepositoryService(
        SqliteRepositoryRegistry(conn),
        paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
    )
    root = init_git_repo(
        tmp_path / "alpha",
        origin="https://github.com/acme/alpha.git",
        files={"src/math.py": "def add(a, b):\n    return a + b\n", "README.md": "alpha\n"},
    )
    enrolled = repos.enrol(str(root), policy_overrides=policy_overrides)
    recorder = Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn))
    goals = GoalService(SqliteGoalStore(conn), repos, recorder)
    planning = PlanningService(
        SqliteGoalStore(conn),
        repos,
        recorder,
        planner or _OkPlanner(),
    )
    if assign_orchestrator:
        provider = models.register_provider(
            ProviderDraft(
                kind="openai_compatible",
                display_name="Local",
                base_url="http://127.0.0.1:11434/v1",
                billed=billed,
                api_key=api_key,
            )
        )
        for item in models.list_profiles():
            models.save_profile(
                ModelProfile(
                    id=item.id,
                    display_name=item.display_name,
                    role=item.role,
                    provider_id=provider.id,
                    model_id="local-chat",
                    billed=billed,
                    approved_fallbacks=(),
                    limits=ResourceLimits(
                        max_tokens=profile_max_tokens,
                        max_attempts=3,
                        timeout_seconds=30.0,
                        cost_ceiling=cost_ceiling,
                        context_window=context_window,
                    ),
                )
            )
        models.assign({role: f"prof_{provider.id}_{role}" for role in MODEL_ROLES})
    indexer = _Indexer(_pack(), [])
    extra: dict[str, object] = {}
    if image_root is not None:
        extra["image_root"] = image_root
    chat = ChatService(
        conn,
        repos,
        goals,
        planning,
        indexer,  # type: ignore[arg-type]
        registry,
        secrets,
        SqliteEventStore(conn),
        complete=complete,  # type: ignore[arg-type]
        stream=stream,  # type: ignore[arg-type]
        **extra,  # type: ignore[arg-type]
    )
    conversation = chat.create_conversation(enrolled.id.value, title="Chat")
    return chat, goals, enrolled, conversation, indexer, conn


def test_slash_goal_always_creates_draft_without_asking_the_model(tmp_path: Path) -> None:
    calls: list[CompletionRequest] = []

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        calls.append(request)
        return CompletionResult(text="should not run", usage=TokenUsage(tokens=1))

    chat, goals, _enrolled, conversation, indexer, _conn = _harness(
        tmp_path, complete=complete, assign_orchestrator=False
    )
    turn = chat.handle_message(
        conversation.id,
        "/goal Fix add\nadd returns a+b for integers",
    )
    listed = goals.list()
    assert len(listed) == 1
    goal = listed[0]
    assert goal.source is GoalSource.CHAT
    assert goal.title == "Fix add"
    assert "add returns a+b" in goal.success_criteria
    assert goal.non_goals == "Do not change unrelated files or skip tests."
    assert goal.risk_ceiling == "low"
    assert goal.max_attempts == 3
    assert turn.goal_refs == (goal.id.value,)
    assert goal.id.value in turn.content
    assert calls == []
    assert indexer.calls == []


def test_answer_path_does_not_create_a_goal_and_maps_citations(tmp_path: Path) -> None:
    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = secret
        assert request.profile.role == "orchestrator"
        assert request.profile.limits.max_tokens == 4096
        return CompletionResult(
            text="add lives in src/math.py",
            usage=TokenUsage(tokens=8),
        )

    chat, goals, enrolled, conversation, indexer, _conn = _harness(
        tmp_path, complete=complete, profile_max_tokens=4096
    )
    turn = chat.handle_message(conversation.id, "Where is add defined?")
    assert list(goals.list()) == []
    assert turn.goal_refs == ()
    assert turn.citations == (
        {"path": "src/math.py", "start_line": 3, "end_line": 12},
    )
    assert "add lives" in turn.content
    assert indexer.calls
    assert indexer.calls[0]["mode"] == "hybrid"
    assert indexer.calls[0]["budget_tokens"] == 6400
    assert indexer.calls[0]["repo_id"] == enrolled.id.value
    assert indexer.calls[0]["query"] == "Where is add defined?"


def test_json_goal_intent_creates_draft_from_envelope(tmp_path: Path) -> None:
    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        return CompletionResult(
            text=json.dumps(
                {
                    "intent": "goal",
                    "title": "Ship login timeout",
                    "success_criteria": "idle sessions last eight hours",
                }
            ),
            usage=TokenUsage(tokens=20),
        )

    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=complete
    )
    turn = chat.handle_message(conversation.id, "please implement a longer login timeout")
    listed = goals.list()
    assert len(listed) == 1
    assert listed[0].title == "Ship login timeout"
    assert listed[0].success_criteria == "idle sessions last eight hours"
    assert listed[0].source is GoalSource.CHAT
    assert turn.goal_refs == (listed[0].id.value,)


def test_invalid_json_is_treated_as_an_answer(tmp_path: Path) -> None:
    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        return CompletionResult(text='{"intent":', usage=TokenUsage(tokens=2))

    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=complete
    )
    turn = chat.handle_message(conversation.id, "what does add do?")
    assert list(goals.list()) == []
    assert turn.goal_refs == ()
    assert turn.content == '{"intent":'


def test_fail_closed_without_orchestrator(tmp_path: Path) -> None:
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, assign_orchestrator=False
    )
    with pytest.raises(OrchestratorNotConfigured, match="Models page"):
        chat.handle_message(conversation.id, "What is add?")


def test_plan_failure_leaves_goal_in_draft_and_includes_error(tmp_path: Path) -> None:
    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, planner=_BoomPlanner(), assign_orchestrator=False
    )
    turn = chat.handle_message(conversation.id, "/goal Repair indexing cache")
    goal = goals.list()[0]
    assert goal.state is GoalState.DRAFT
    assert "planner exploded" in turn.content
    assert turn.goal_refs == (goal.id.value,)


def test_max_attempts_come_from_repository_policy(tmp_path: Path) -> None:
    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        assign_orchestrator=False,
        policy_overrides={"budgets": {"max_attempts_per_issue": 5}},
    )
    chat.handle_message(conversation.id, "/goal Only the title")
    assert goals.list()[0].max_attempts == 5
    assert goals.list()[0].success_criteria == "Only the title"


def test_get_conversation_appends_idempotent_goal_progress(tmp_path: Path) -> None:
    chat, goals, _enrolled, conversation, _indexer, conn = _harness(
        tmp_path, planner=_OkPlanner(), assign_orchestrator=False
    )
    chat.handle_message(conversation.id, "/goal Fix add\nadd returns a+b")
    goal = goals.list()[0]
    first = chat.get_conversation(conversation.id)
    progress = [item for item in first.messages if item.role == "system"]
    assert progress
    assert any(goal.id.value in item.content for item in progress)
    events = SqliteEventStore(conn).list_after(0)
    linked = [
        item
        for item in events
        if str(item.payload.get("goal_id")) == goal.id.value
        and (item.type.startswith("goal.") or item.type.startswith("task."))
    ]
    assert linked
    second = chat.get_conversation(conversation.id)
    system_ids = [item.id for item in second.messages if item.role == "system"]
    assert system_ids == [item.id for item in progress]
    assert len(system_ids) == len(set(system_ids))


def test_billed_orchestrator_without_secret_fails_closed(tmp_path: Path) -> None:
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, billed=True, api_key=None, cost_ceiling=1.0
    )
    with pytest.raises(OrchestratorNotConfigured, match="Models page"):
        chat.handle_message(conversation.id, "What is add?")


def test_unbilled_orchestrator_without_secret_can_complete(tmp_path: Path) -> None:
    seen: list[object] = []

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        seen.append(secret)
        _ = request
        return CompletionResult(text="hello from ollama", usage=TokenUsage(tokens=3))

    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=complete, billed=False, api_key=None
    )
    turn = chat.handle_message(conversation.id, "What is add?")
    assert list(goals.list()) == []
    assert turn.content == "hello from ollama"
    assert seen == [None]


def test_secret_store_error_is_orchestrator_not_configured(tmp_path: Path) -> None:
    class _BoomStore:
        def put(self, name: str, value: str) -> None:
            _ = name, value

        def get(self, name: str) -> str | None:
            _ = name
            raise SecretStoreError("OS credential storage could not read the secret")

        def delete(self, name: str) -> None:
            _ = name

    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        billed=True,
        api_key="sk-paid",
        cost_ceiling=1.0,
        secrets=_BoomStore(),  # type: ignore[arg-type]
    )
    with pytest.raises(OrchestratorNotConfigured, match="Models page"):
        chat.handle_message(conversation.id, "What is add?")


def test_billed_cost_ceiling_is_orchestrator_not_configured(tmp_path: Path) -> None:
    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        raise AssertionError("must not call the model when the cost ceiling blocks billed use")

    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        complete=complete,
        billed=True,
        api_key="sk-paid",
        cost_ceiling=0.0,
    )
    with pytest.raises(OrchestratorNotConfigured, match="Models page"):
        chat.handle_message(conversation.id, "What is add?")


def test_json_answer_envelope_is_not_streamed_or_stored(tmp_path: Path) -> None:
    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        return CompletionResult(
            text='{"intent":"answer","text":"hello"}',
            usage=TokenUsage(tokens=5),
        )

    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=complete
    )
    tokens: list[str] = []
    final: ChatTurn | None = None
    for item in chat.stream_message(conversation.id, "hi"):
        if isinstance(item, str):
            tokens.append(item)
        elif isinstance(item, ChatTurn):
            final = item
    visible = "".join(tokens)
    assert visible == "hello"
    assert "{" not in visible
    assert final is not None
    assert final.content == "hello"
    stored = [
        item
        for item in chat.get_conversation(conversation.id).messages
        if item.role == "assistant"
    ]
    assert stored[-1].content == "hello"
    assert visible == stored[-1].content


def test_json_goal_envelope_is_not_streamed(tmp_path: Path) -> None:
    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        return CompletionResult(
            text=json.dumps(
                {
                    "intent": "goal",
                    "title": "Ship login timeout",
                    "success_criteria": "idle sessions last eight hours",
                }
            ),
            usage=TokenUsage(tokens=20),
        )

    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=complete
    )
    tokens: list[str] = []
    final: ChatTurn | None = None
    for item in chat.stream_message(conversation.id, "please implement a longer login timeout"):
        if isinstance(item, str):
            tokens.append(item)
        elif isinstance(item, ChatTurn):
            final = item
    visible = "".join(tokens)
    assert "{" not in visible
    assert "intent" not in visible
    assert final is not None
    assert visible == final.content
    assert "Draft goal" in visible
    assert goals.list()
    stored = [
        item
        for item in chat.get_conversation(conversation.id).messages
        if item.role == "assistant"
    ]
    assert stored[-1].content == visible


def test_stream_message_syncs_progress_into_model_history(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = secret
        captured.append(request)
        return CompletionResult(text="the delegated work is planned", usage=TokenUsage(tokens=4))

    chat, goals, _enrolled, conversation, _indexer, conn = _harness(
        tmp_path, planner=_OkPlanner(), complete=complete
    )
    chat.handle_message(conversation.id, "/goal Fix add\nadd returns a+b")
    goal = goals.list()[0]
    assert captured == []
    chat.handle_message(conversation.id, "what happened to the delegated work?")
    assert captured
    payload = captured[0].messages
    assert payload is not None
    assert any(item.get("role") == "user" for item in payload)
    assert any(item.get("role") == "assistant" for item in payload)
    progress = [
        item
        for item in payload
        if item.get("role") == "system" and goal.id.value in str(item.get("content", ""))
    ]
    assert progress
    assert any(
        "goal." in str(item.get("content", "")) or "task." in str(item.get("content", ""))
        for item in progress
    )
    stored = SqliteEventStore(conn).list_after(0)
    assert any(str(item.payload.get("goal_id")) == goal.id.value for item in stored)


def test_stream_message_yields_each_delta_before_final_turn(tmp_path: Path) -> None:
    def stream(request: CompletionRequest, secret: object):
        _ = request, secret
        yield "Hel"
        yield "lo"

    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(tmp_path, stream=stream)
    tokens: list[str] = []
    final: ChatTurn | None = None
    for item in chat.stream_message(conversation.id, "Say hello"):
        if isinstance(item, str):
            tokens.append(item)
        elif isinstance(item, ChatTurn):
            final = item
    assert tokens == ["Hel", "lo"]
    assert final is not None
    assert final.content == "Hello"
    assert list(goals.list()) == []
    stored = [
        item
        for item in chat.get_conversation(conversation.id).messages
        if item.role == "assistant"
    ]
    assert stored[-1].content == "Hello"


def _scripted(replies: list[str], captured: list[CompletionRequest] | None = None):
    remaining = list(replies)

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = secret
        if captured is not None:
            captured.append(request)
        return CompletionResult(text=remaining.pop(0), usage=TokenUsage(tokens=8))

    return complete


def _system_text(request: CompletionRequest) -> str:
    assert request.messages is not None
    first = request.messages[0]
    content = first.get("content")
    assert isinstance(content, str)
    return content


def _python_script(root: Path, name: str, source: str) -> str:
    (root / name).write_text(source, encoding="utf-8")
    return f'"{sys.executable}" {name}'


def _roles(chat: ChatService, conversation_id: str) -> list[str]:
    return [item.role for item in chat.get_conversation(conversation_id).messages]


def test_stores_user_and_assistant_turns(tmp_path: Path) -> None:
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Staff is missing before the calendar route."])
    )
    turn = chat.handle_message(conversation.id, "What is broken in onboarding?")
    assert _roles(chat, conversation.id)[-2:] == ["user", "assistant"]
    stored = chat.get_conversation(conversation.id).messages
    assert stored[-2].content == "What is broken in onboarding?"
    assert "calendar" in stored[-1].content
    assert "calendar" in turn.content


def test_pasted_image_shown_to_the_model(tmp_path: Path) -> None:
    import base64

    captured: list[CompletionRequest] = []
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        complete=_scripted(["That is a one pixel screenshot."], captured),
        image_root=tmp_path / "chat_images",
    )
    chat.handle_message(
        conversation.id,
        "What is this?",
        images=[{"mime": "image/png", "data": TINY_PNG_B64}],
    )
    user = next(
        item for item in chat.get_conversation(conversation.id).messages if item.role == "user"
    )
    assert "What is this?" in user.content
    assert "kronos-image:" in user.content
    assert captured
    assert captured[0].messages is not None
    user_msg = [item for item in captured[0].messages if item.get("role") == "user"][-1]
    parts = user_msg.get("content")
    assert isinstance(parts, list)
    assert any(part.get("type") == "image_url" for part in parts if isinstance(part, dict))
    assert base64.b64decode(TINY_PNG_B64)


def test_rejects_blank_text_without_images(tmp_path: Path) -> None:
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["unused"])
    )
    with pytest.raises(ValueError, match="message is required"):
        chat.handle_message(conversation.id, "   ")


def test_tool_round_records_search_then_final_answer(tmp_path: Path) -> None:
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        complete=_scripted(
            [
                '```tool\n{"name": "search_index", "query": "onboarding"}\n```',
                "Hits are in the packed context.",
            ]
        ),
    )
    chat.handle_message(conversation.id, "Search the workspace.")
    messages = [
        item
        for item in chat.get_conversation(conversation.id).messages
        if item.role in {"user", "tool", "assistant"}
    ]
    assert [item.role for item in messages[-3:]] == ["user", "tool", "assistant"]
    tool = messages[-2]
    assert tool.tool_name == "search_index"
    assert tool.tool_status == "ok"
    assert tool.tool_json is not None
    assert "query" in tool.tool_json
    assert "Hits are in the packed context." in messages[-1].content


def test_cancel_stops_before_running_more_tools(tmp_path: Path) -> None:
    ids: list[str] = []

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        request_cancel(ids[0])
        return CompletionResult(
            text='```tool\n{"name": "list_goals"}\n```',
            usage=TokenUsage(tokens=1),
        )

    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(tmp_path, complete=complete)
    ids.append(conversation.id)
    chat.handle_message(conversation.id, "Start work")
    messages = chat.get_conversation(conversation.id).messages
    assert not any(item.role == "tool" for item in messages)
    assert any("Stopped" in item.content for item in messages if item.role == "assistant")


def test_write_file_stays_inside_workspace_and_rejects_escape(tmp_path: Path) -> None:
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        complete=_scripted(
            [
                '```tool\n{"name": "write_file", "path": "hello.py", "content": "new\\n"}\n```',
                "Updated hello.py.",
            ]
        ),
    )
    root = Path(enrolled.realpath)
    chat.handle_message(conversation.id, "Patch hello.py")
    assert (root / "hello.py").read_text(encoding="utf-8") == "new\n"
    messages = chat.get_conversation(conversation.id).messages
    assert any(item.tool_name == "write_file" and item.tool_status == "ok" for item in messages)

    chat2, _goals2, enrolled2, conversation2, _indexer2, _conn2 = _harness(
        tmp_path / "escape",
        complete=_scripted(
            [
                '```tool\n{"name": "write_file", "path": "../secret.txt", "content": "nope"}\n```',
                "I will not write outside the folder.",
            ]
        ),
    )
    chat2.handle_message(conversation2.id, "Escape")
    assert not (tmp_path / "escape" / "secret.txt").exists()
    assert not (Path(enrolled2.realpath).parent / "secret.txt").exists()


def test_write_file_records_a_workspace_diff(tmp_path: Path) -> None:
    chat, _goals, enrolled, conversation, _indexer, conn = _harness(
        tmp_path,
        complete=_scripted(
            [
                '```tool\n{"name": "write_file", "path": "hello.py", "content": "new\\n"}\n```',
                "Updated hello.py.",
            ]
        ),
    )
    chat.handle_message(conversation.id, "Patch hello.py")
    wrote = [item for item in SqliteEventStore(conn).list_after(0) if item.type == "git.wrote"]
    assert wrote
    payload = dict(wrote[0].payload)
    assert payload["path"] == "hello.py"
    assert payload["repository_id"] == enrolled.id.value
    assert "hello.py" in str(payload["summary"])
    patch = str(payload["patch"])
    assert "+new" in patch


def test_write_file_keeps_a_backup_for_inspector_revert(tmp_path: Path) -> None:
    chat, _goals, enrolled, conversation, _indexer, conn = _harness(
        tmp_path,
        complete=_scripted(
            [
                '```tool\n{"name": "write_file", "path": "hello.py", "content": "new\\n"}\n```',
                "Updated hello.py.",
            ]
        ),
    )
    (Path(enrolled.realpath) / "hello.py").write_text("old\n", encoding="utf-8")
    chat.handle_message(conversation.id, "Patch hello.py")
    from kronos_engine.state.conversations import SqliteConversationStore

    backup = SqliteConversationStore(conn).get_file_backup(enrolled.id.value, "hello.py")
    assert backup == "old\n"


def test_active_memories_are_injected_into_the_system_prompt(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, _enrolled, conversation, _indexer, conn = _harness(
        tmp_path, complete=_scripted(["I will guard the calendar route."], captured)
    )
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
    chat.handle_message(conversation.id, "Fix onboarding")
    assert "Never send onboarding to the calendar" in _system_text(captured[0])


def test_persist_streamed_tokens_before_complete_returns(tmp_path: Path) -> None:
    snapshots: list[tuple[str, ...]] = []
    ids: list[str] = []
    holder: list[ChatService] = []

    def stream(request: CompletionRequest, secret: object):
        _ = request, secret
        yield "partial-token"
        stored = holder[0].get_conversation(ids[0])
        snapshots.append(tuple(item.content for item in stored.messages))
        yield " and more"

    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(tmp_path, stream=stream)
    ids.append(conversation.id)
    holder.append(chat)
    turn = chat.handle_message(conversation.id, "Hi")
    assert snapshots
    assert any("partial-token" in item for item in snapshots[0])
    assert turn.content == "partial-token and more"


def test_cancel_during_stream_keeps_partial_and_stops(tmp_path: Path) -> None:
    ids: list[str] = []

    def stream(request: CompletionRequest, secret: object):
        _ = request, secret
        yield "Hi from the model"
        request_cancel(ids[0])

    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(tmp_path, stream=stream)
    ids.append(conversation.id)
    chat.handle_message(conversation.id, "Go")
    assistant = [
        item
        for item in chat.get_conversation(conversation.id).messages
        if item.role == "assistant"
    ]
    assert assistant
    assert "Hi from the model" in assistant[-1].content
    assert "Stopped" in assistant[-1].content
    assert not any(item.role == "tool" for item in chat.get_conversation(conversation.id).messages)


def test_mentioned_file_attached_to_system_prompt(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Looks fine."], captured)
    )
    (Path(enrolled.realpath) / "hello.py").write_text("print('ok')\n", encoding="utf-8")
    chat.handle_message(conversation.id, "Review @hello.py")
    system = _system_text(captured[0])
    assert "hello.py" in system
    assert "print('ok')" in system


def test_escaped_mention_not_attached(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Denied."], captured)
    )
    (Path(enrolled.realpath).parent / "secret.txt").write_text("nope\n", encoding="utf-8")
    chat.handle_message(conversation.id, "See @../secret.txt")
    assert "nope" not in _system_text(captured[0])


def test_run_command_uses_workspace_cwd(tmp_path: Path) -> None:
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["placeholder"])
    )
    root = Path(enrolled.realpath)
    (root / "marker.txt").write_text("from-workspace\n", encoding="utf-8")
    command = _python_script(
        root,
        "probe.py",
        "from pathlib import Path\nprint(Path('marker.txt').read_text())\n",
    )
    fence = "```tool\n" + json.dumps({"name": "run_command", "command": command}) + "\n```"
    chat2, _g, _e, conversation2, _i, _c = _harness(
        tmp_path / "cwd",
        complete=_scripted([fence, "The marker is in the workspace."]),
    )
    root2 = Path(_e.realpath)
    (root2 / "marker.txt").write_text("from-workspace\n", encoding="utf-8")
    _python_script(
        root2,
        "probe.py",
        "from pathlib import Path\nprint(Path('marker.txt').read_text())\n",
    )
    command2 = f'"{sys.executable}" probe.py'
    fence2 = "```tool\n" + json.dumps({"name": "run_command", "command": command2}) + "\n```"
    chat3, _g3, enrolled3, conversation3, _i3, _c3 = _harness(
        tmp_path / "cwd2",
        complete=_scripted([fence2, "The marker is in the workspace."]),
    )
    root3 = Path(enrolled3.realpath)
    (root3 / "marker.txt").write_text("from-workspace\n", encoding="utf-8")
    (root3 / "probe.py").write_text(
        "from pathlib import Path\nprint(Path('marker.txt').read_text())\n",
        encoding="utf-8",
    )
    messages = chat3.handle_message(conversation3.id, "Run probe.py")
    _ = chat, conversation, conversation2, messages
    tool = next(
        item
        for item in chat3.get_conversation(conversation3.id).messages
        if item.tool_name == "run_command"
    )
    assert tool.tool_status == "ok"
    assert "from-workspace" in (tool.content + (tool.tool_json or ""))
    assert "Exit 0" in (tool.content + (tool.tool_json or ""))


def test_run_command_needs_an_open_workspace(tmp_path: Path) -> None:
    chat, _goals, _enrolled, _conversation, _indexer, _conn = _harness(
        tmp_path,
        complete=_scripted(
            [
                '```tool\n{"name": "run_command", "command": "echo hi"}\n```',
                "Open a folder first.",
            ]
        ),
    )
    loose = chat.create_conversation(None, title="Loose")
    chat.handle_message(loose.id, "Run echo")
    tool = next(
        item
        for item in chat.get_conversation(loose.id).messages
        if item.tool_name == "run_command"
    )
    assert "git folder" in tool.content.lower() or "workspace" in tool.content.lower()


def test_run_command_caps_per_turn(tmp_path: Path) -> None:
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["x"])
    )
    _ = chat, conversation
    root_holder: list[Path] = []

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        command = _python_script(
            root_holder[0],
            "tick.py",
            "from pathlib import Path\n"
            "p = Path('ticks.txt')\n"
            "prior = p.read_text(encoding='utf-8') if p.exists() else ''\n"
            "p.write_text(prior + 'x', encoding='utf-8')\n",
        )
        fence = "```tool\n" + json.dumps({"name": "run_command", "command": command}) + "\n```"
        remaining = getattr(complete, "left")
        if remaining <= 1:
            complete.left = remaining - 1  # type: ignore[attr-defined]
            return CompletionResult(text="Done.", usage=TokenUsage(tokens=1))
        complete.left = remaining - 1  # type: ignore[attr-defined]
        return CompletionResult(text=fence, usage=TokenUsage(tokens=1))

    complete.left = 7  # type: ignore[attr-defined]
    chat2, _g, enrolled2, conversation2, _i, _c = _harness(tmp_path / "cap", complete=complete)
    root_holder.append(Path(enrolled2.realpath))
    _ = enrolled
    chat2.handle_message(conversation2.id, "Tick six times")
    assert (Path(enrolled2.realpath) / "ticks.txt").read_text(encoding="utf-8") == "xxxxx"
    bodies = [
        item.content + (item.tool_json or "")
        for item in chat2.get_conversation(conversation2.id).messages
        if item.tool_name == "run_command"
    ]
    assert any("5 commands" in body for body in bodies)


def test_run_command_stops_when_cancelled(tmp_path: Path) -> None:
    fence_holder: list[str] = []
    ids: list[str] = []
    started_holder: list[Path] = []

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        if getattr(complete, "first", True):
            complete.first = False  # type: ignore[attr-defined]
            return CompletionResult(text=fence_holder[0], usage=TokenUsage(tokens=1))
        return CompletionResult(text="Should not keep going.", usage=TokenUsage(tokens=1))

    complete.first = True  # type: ignore[attr-defined]
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=complete
    )
    root = Path(enrolled.realpath)
    command = _python_script(
        root,
        "sleep.py",
        "from pathlib import Path\n"
        "import time\n"
        "Path('started.txt').write_text('1')\n"
        "time.sleep(8)\n",
    )
    fence = "```tool\n" + json.dumps({"name": "run_command", "command": command}) + "\n```"
    fence_holder.append(fence)
    ids.append(conversation.id)
    started = root / "started.txt"
    started_holder.append(started)

    def stop_after_start() -> None:
        for _ in range(80):
            if started.exists():
                request_cancel(conversation.id)
                return
            threading.Event().wait(0.05)
        raise AssertionError("command did not start")

    stopper = threading.Thread(target=stop_after_start)
    stopper.start()
    chat.handle_message(conversation.id, "Run sleep")
    stopper.join(timeout=2)
    messages = chat.get_conversation(conversation.id).messages
    tool = next(item for item in messages if item.tool_name == "run_command")
    blob = tool.content + (tool.tool_json or "")
    assert "Stopped." in blob
    assert not any("Should not keep going." in item.content for item in messages)


def test_workspace_instructions_in_system_prompt(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Understood."], captured)
    )
    root = Path(enrolled.realpath)
    (root / "AGENTS.md").write_text("Never commit to main.\n", encoding="utf-8")
    (root / "src" / "AGENTS.md").write_text("Nested secret rule.\n", encoding="utf-8")
    chat.handle_message(conversation.id, "What should I remember?")
    system = _system_text(captured[0])
    assert "Workspace instructions:" in system
    assert "Never commit to main." in system
    assert "Nested secret rule." not in system


def test_cursor_rules_in_system_prompt(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Understood."], captured)
    )
    root = Path(enrolled.realpath)
    rules = root / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "python.mdc").write_text("Use type hints.\n", encoding="utf-8")
    (root / ".cursorrules").write_text("No em dashes in UI copy.\n", encoding="utf-8")
    chat.handle_message(conversation.id, "How should I write code?")
    system = _system_text(captured[0])
    assert "No em dashes in UI copy." in system
    assert "Use type hints." in system
    assert ".cursor/rules/python.mdc" in system


def test_omits_workspace_instructions_when_none_exist(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Hello."], captured)
    )
    chat.handle_message(conversation.id, "Hi")
    assert "Workspace instructions:" not in _system_text(captured[0])


def test_skips_nested_cursor_rule_directories(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Understood."], captured)
    )
    root = Path(enrolled.realpath)
    rules = root / ".cursor" / "rules"
    nested = rules / "team"
    nested.mkdir(parents=True)
    (nested / "extra.md").write_text("Do not include nested.\n", encoding="utf-8")
    (rules / "root.md").write_text("Keep this.\n", encoding="utf-8")
    chat.handle_message(conversation.id, "Which rules apply?")
    system = _system_text(captured[0])
    assert "Keep this." in system
    assert "Do not include nested." not in system


def test_caps_workspace_instruction_size(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["Trimmed."], captured)
    )
    (Path(enrolled.realpath) / "AGENTS.md").write_text("A" * 50_000, encoding="utf-8")
    chat.handle_message(conversation.id, "Go")
    system = _system_text(captured[0])
    assert system.count("A") <= 12_000
    assert "Workspace instructions:" in system


def test_delta_suppression_holds_tool_fence_and_emits_prefix(tmp_path: Path) -> None:
    rounds = [
        ["Hello ", "`", "``", 'tool\n{"name": "list_goals"}\n```'],
        ["No goals yet."],
    ]

    def stream(request: CompletionRequest, secret: object):
        _ = request, secret
        yield from rounds.pop(0)

    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(tmp_path, stream=stream)
    tokens: list[str] = []
    tools: list[ToolEvent] = []
    for item in chat.stream_message(conversation.id, "Search then answer"):
        if isinstance(item, str):
            tokens.append(item)
        elif isinstance(item, ToolEvent):
            tools.append(item)
    visible = "".join(tokens)
    assert "Hello " in visible
    assert "```tool" not in visible
    assert any(item.status == "running" and item.name == "list_goals" for item in tools)
    assert any(item.status == "ok" and item.name == "list_goals" for item in tools)


def test_list_files_tool_lists_workspace_paths(tmp_path: Path) -> None:
    chat, _goals, enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        complete=_scripted(
            [
                '```tool\n{"name": "list_files", "glob": "*.md"}\n```',
                "README is present.",
            ]
        ),
    )
    _ = enrolled
    chat.handle_message(conversation.id, "List markdown")
    tool = next(
        item
        for item in chat.get_conversation(conversation.id).messages
        if item.tool_name == "list_files"
    )
    blob = tool.content + (tool.tool_json or "")
    assert "README.md" in blob
    assert "src/math.py" not in blob


def test_history_trimmed_to_context_window(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path,
        complete=_scripted(["one", "two"], captured),
        context_window=80,
        profile_max_tokens=8,
    )
    chat.handle_message(conversation.id, "FIRST_UNIQUE_TOKEN " + ("x" * 200))
    chat.handle_message(conversation.id, "second question")
    second = captured[1]
    blob = json.dumps(list(second.messages or ()))
    assert "FIRST_UNIQUE_TOKEN" not in blob
    assert "second question" in blob


def test_goal_reply_includes_readiness_lines(tmp_path: Path) -> None:
    chat, goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, assign_orchestrator=False
    )
    items = list(chat.stream_message(conversation.id, "/goal Fix add\nadd returns a+b"))
    turn = next(item for item in items if isinstance(item, ChatTurn))
    event = next(item for item in items if isinstance(item, GoalEvent))
    goal = goals.list()[0]
    assert f"Draft goal `{goal.id.value}` created." in turn.content
    assert "Reviewer app:" in turn.content
    assert "can execute" in turn.content.lower() or "cannot execute" in turn.content.lower()
    assert event.id == goal.id.value
    assert event.readiness


def test_no_workspace_conversation_answers(tmp_path: Path) -> None:
    chat, _goals, _enrolled, _conversation, indexer, _conn = _harness(
        tmp_path, complete=_scripted(["hello from nowhere"])
    )
    loose = chat.create_conversation(None, title="Loose")
    turn = chat.handle_message(loose.id, "What is add?")
    assert turn.content == "hello from nowhere"
    assert indexer.calls == [] or all(
        call.get("repo_id") not in {None, ""} for call in indexer.calls
    )


def test_no_workspace_tool_returns_a_clear_sentence(tmp_path: Path) -> None:
    chat, _goals, _enrolled, _conversation, indexer, _conn = _harness(
        tmp_path,
        complete=_scripted(
            [
                '```tool\n{"name": "search_index", "query": "add"}\n```',
                "I cannot search without a folder.",
            ]
        ),
    )
    loose = chat.create_conversation(None, title="Loose")
    chat.handle_message(loose.id, "Search add")
    tool = next(
        item
        for item in chat.get_conversation(loose.id).messages
        if item.tool_name == "search_index"
    )
    assert "workspace" in tool.content.lower() or "git folder" in tool.content.lower()
    assert indexer.calls == []


def test_slash_goal_system_prompt_mentions_unattended_work(tmp_path: Path) -> None:
    captured: list[CompletionRequest] = []
    chat, _goals, _enrolled, conversation, _indexer, _conn = _harness(
        tmp_path, complete=_scripted(["ok"], captured)
    )
    chat.handle_message(conversation.id, "hello")
    system = _system_text(captured[0])
    assert "/goal" in system
    assert "skill summaries" in system.lower()
