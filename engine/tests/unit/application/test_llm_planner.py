# SPDX-License-Identifier: AGPL-3.0-or-later
"""LlmPlanner uses the planner role model and falls back to IndexedPlanner."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tests.support.secrets import InMemorySecretStore

from kronos_engine.application.model_profiles import ModelProfileService, ProviderDraft
from kronos_engine.application.planning import IndexedPlanner, LlmPlanner
from kronos_engine.domain.entities import GoalId, RepositoryId
from kronos_engine.domain.goals import GoalRecord, GoalSource, GoalState
from kronos_engine.domain.models import MODEL_ROLES, ModelProfile, ResourceLimits
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult, TokenUsage
from kronos_engine.state.database import Database
from kronos_engine.state.model_profiles import SqliteModelRegistry


def _goal() -> GoalRecord:
    return GoalRecord(
        id=GoalId("goal_plan"),
        repository_id=RepositoryId("repo_alpha"),
        title="Fix add",
        success_criteria="add returns a+b",
        non_goals="rewrite the parser",
        risk_ceiling="low",
        source=GoalSource.DESKTOP,
        state=GoalState.DRAFT,
    )


def _valid_plan() -> dict[str, object]:
    return {
        "tasks": [
            {
                "id": "task_goal_plan",
                "title": "Fix add",
                "kind": "implementation",
                "depends_on": [],
                "evidence": [{"path": "src/math.py", "line": 3}],
                "size": "S",
                "baseline_size": "S",
                "risk": "low",
                "scope_paths": ["src/math.py"],
            }
        ]
    }


class _Indexer:
    def list_chunks(self, repository_id: str) -> tuple[object, ...]:
        _ = repository_id
        return (SimpleNamespace(path="src/fallback.py", start_line=1),)


class _Transport:
    def __init__(self) -> None:
        self.posts: list[dict[str, object]] = []

    def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]:
        _ = url, timeout
        return 200, {}

    def post(
        self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, object]]:
        self.posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return 200, {"choices": [{"message": {"content": "nope"}}], "usage": {"total_tokens": 1}}


def _service(tmp_path: Path) -> tuple[ModelProfileService, InMemorySecretStore]:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    store = InMemorySecretStore()
    return ModelProfileService(SqliteModelRegistry(conn), store), store


def test_valid_json_from_planner_model_is_used(tmp_path: Path) -> None:
    service, secrets = _service(tmp_path)
    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
            api_key="sk-planner",
        )
    )
    profiles = {item.role: item.id for item in service.list_profiles()}
    service.assign(profiles)
    calls: list[CompletionRequest] = []

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        calls.append(request)
        assert secret is not None
        return CompletionResult(text=json.dumps(_valid_plan()), usage=TokenUsage(tokens=12))

    planner = LlmPlanner(
        service._registry,
        secrets,
        IndexedPlanner(_Indexer()),
        complete=complete,
    )
    planned = planner.plan(_goal())
    assert planned == _valid_plan()
    assert calls
    assert calls[0].profile.role == "planner"


def test_invalid_json_and_missing_model_fall_back_to_indexed(tmp_path: Path) -> None:
    service, secrets = _service(tmp_path)
    fallback = IndexedPlanner(_Indexer())
    missing = LlmPlanner(service._registry, secrets, fallback)
    assert planner_scope_path(missing.plan(_goal())) == "src/fallback.py"

    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
            api_key="sk-planner",
        )
    )
    profiles = {item.role: item.id for item in service.list_profiles()}
    service.assign(profiles)

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        return CompletionResult(text="not-json", usage=TokenUsage(tokens=1))

    invalid = LlmPlanner(service._registry, secrets, fallback, complete=complete)
    assert planner_scope_path(invalid.plan(_goal())) == "src/fallback.py"


def test_billed_ceiling_zero_does_not_call_network(tmp_path: Path) -> None:
    service, secrets = _service(tmp_path)
    provider = service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            billed=True,
            api_key="sk-paid",
        )
    )
    for item in service.list_profiles():
        service.save_profile(
            ModelProfile(
                id=item.id,
                display_name=item.display_name,
                role=item.role,
                provider_id=provider.id,
                model_id="gpt-4o-mini",
                billed=True,
                approved_fallbacks=(),
                limits=ResourceLimits(
                    max_tokens=128, max_attempts=3, timeout_seconds=15.0, cost_ceiling=0.0
                ),
            )
        )
    service.assign({role: f"prof_{provider.id}_{role}" for role in MODEL_ROLES})
    transport = _Transport()
    planner = LlmPlanner(
        service._registry,
        secrets,
        IndexedPlanner(_Indexer()),
        transport=transport,
    )
    planned = planner.plan(_goal())
    assert transport.posts == []
    assert planner_scope_path(planned) == "src/fallback.py"


def test_composition_wires_llm_planner_around_indexed_fallback() -> None:
    engine_src = Path(__file__).resolve().parents[3] / "src" / "kronos_engine"
    composition = (engine_src / "application" / "composition.py").read_text(encoding="utf-8")
    assert "LlmPlanner" in composition
    assert "IndexedPlanner" in composition
    assert "select_executor" in composition


def planner_scope_path(planned: object) -> str:
    assert isinstance(planned, dict)
    tasks = planned["tasks"]
    assert isinstance(tasks, list)
    first = tasks[0]
    assert isinstance(first, dict)
    paths = first["scope_paths"]
    assert isinstance(paths, list)
    return str(paths[0])
