# SPDX-License-Identifier: AGPL-3.0-or-later
"""ChatService routes /goal to draft goals and answers with citations. No GitHub."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.adapters.secrets.os_store import SecretStoreError
from kronos_engine.application.chat import ChatService, ChatTurn, OrchestratorNotConfigured
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
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult, TokenUsage
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.model_profiles import SqliteModelRegistry
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry


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
    assign_orchestrator: bool = True,
    profile_max_tokens: int = 4096,
    policy_overrides: dict[str, object] | None = None,
    billed: bool = False,
    api_key: str | None = "sk-chat",
    cost_ceiling: float = 0.0,
    secrets: InMemorySecretStore | None = None,
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
                    ),
                )
            )
        models.assign({role: f"prof_{provider.id}_{role}" for role in MODEL_ROLES})
    indexer = _Indexer(_pack(), [])
    chat = ChatService(
        conn,
        repos,
        goals,
        planning,
        indexer,  # type: ignore[arg-type]
        registry,
        secrets,
        SqliteEventStore(conn),
        complete=complete,
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
        assert request.profile.limits.max_tokens <= 1024
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
    assert indexer.calls[0]["budget_tokens"] == 2000
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
        else:
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
        else:
            final = item
    visible = "".join(tokens)
    assert "{" not in visible
    assert "intent" not in visible
    assert final is not None
    assert visible == final.content
    assert "Created draft goal" in visible
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
