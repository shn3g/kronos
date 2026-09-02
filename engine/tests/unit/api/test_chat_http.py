# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conversation HTTP: auth, lifecycle, SSE messages, and chat→goal handoff."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore

from kronos_engine.adapters.secrets.os_store import SecretStoreError
from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult, TokenUsage
from kronos_engine.state.database import Database

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _settings(tmp_path: Path) -> Settings:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    return Settings(
        engine_version="0.1.0",
        min_client_version="0.1.0",
        bind_host="127.0.0.1",
        bind_port=0,
        auth_token="install-token",
        paths=paths,
    )


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, dict[str, str], Path]]:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=InMemorySecretStore())
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    try:
        yield http, {"Authorization": "Bearer install-token"}, tmp_path
    finally:
        await http.aclose()


async def _enrol(http: AsyncClient, headers: dict[str, str], root: Path) -> str:
    enrolled = await http.post("/repositories", json={"path": str(root)}, headers=headers)
    assert enrolled.status_code == 200
    return str(enrolled.json()["repository"]["id"])


@pytest.mark.asyncio
async def test_conversations_require_auth_and_lifecycle(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    alpha = init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
    beta = init_git_repo(tmp_path / "beta", files={"README.md": "beta\n"})
    alpha_id = await _enrol(http, headers, alpha)
    beta_id = await _enrol(http, headers, beta)

    unauth = await http.post(f"/repositories/{alpha_id}/conversations", json={})
    assert unauth.status_code == 401

    missing_repo = await http.post(
        "/repositories/repo_missing/conversations", json={}, headers=headers
    )
    assert missing_repo.status_code == 404

    created = await http.post(
        f"/repositories/{alpha_id}/conversations",
        json={"title": "Ask alpha"},
        headers=headers,
    )
    assert created.status_code == 200
    conversation = created.json()
    cid = conversation["id"]
    assert conversation["repository_id"] == alpha_id
    assert conversation["title"] == "Ask alpha"

    listed_alpha = await http.get(f"/repositories/{alpha_id}/conversations", headers=headers)
    assert listed_alpha.status_code == 200
    assert [item["id"] for item in listed_alpha.json()["conversations"]] == [cid]

    listed_beta = await http.get(f"/repositories/{beta_id}/conversations", headers=headers)
    assert listed_beta.status_code == 200
    assert listed_beta.json()["conversations"] == []

    detail = await http.get(f"/conversations/{cid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["conversation"]["id"] == cid
    assert detail.json()["messages"] == []

    unknown = await http.get("/conversations/conv_missing", headers=headers)
    assert unknown.status_code == 404

    deleted = await http.delete(f"/conversations/{cid}", headers=headers)
    assert deleted.status_code == 200
    gone = await http.get(f"/conversations/{cid}", headers=headers)
    assert gone.status_code == 404
    empty = await http.get(f"/repositories/{alpha_id}/conversations", headers=headers)
    assert empty.json()["conversations"] == []


@pytest.mark.asyncio
async def test_goal_handoff_creates_a_real_goal_row(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    root = init_git_repo(
        tmp_path / "alpha",
        files={"src/math.py": "def add(a, b):\n    return a + b\n"},
    )
    repo_id = await _enrol(http, headers, root)
    created = await http.post(f"/repositories/{repo_id}/conversations", json={}, headers=headers)
    cid = created.json()["id"]

    async with http.stream(
        "POST",
        f"/conversations/{cid}/messages",
        json={"content": "/goal Fix add\nadd returns a+b"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        payload = await _read_sse(response)

    assert payload["goal_refs"]
    goal_id = payload["goal_refs"][0]
    goals = await http.get("/goals", headers=headers)
    assert goals.status_code == 200
    rows = goals.json()["goals"]
    assert len(rows) == 1
    assert rows[0]["id"] == goal_id
    assert rows[0]["source"] == "chat"
    assert rows[0]["title"] == "Fix add"
    assert rows[0]["repository_id"] == repo_id

    detail = await http.get(f"/conversations/{cid}", headers=headers)
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    roles = [item["role"] for item in messages]
    assert "user" in roles
    assert "assistant" in roles
    assistant = next(item for item in messages if item["role"] == "assistant")
    assert goal_id in assistant["goal_refs"]


@pytest.mark.asyncio
async def test_answer_without_orchestrator_is_conflict(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    root = init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
    repo_id = await _enrol(http, headers, root)
    created = await http.post(f"/repositories/{repo_id}/conversations", json={}, headers=headers)
    cid = created.json()["id"]
    response = await http.post(
        f"/conversations/{cid}/messages",
        json={"content": "What is add?"},
        headers=headers,
    )
    assert response.status_code in {400, 409}
    detail = response.json()["detail"]
    assert "Models page" in str(detail)


@pytest.mark.asyncio
async def test_billed_orchestrator_without_secret_is_conflict(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    root = init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
    repo_id = await _enrol(http, headers, root)
    created = await http.post(f"/repositories/{repo_id}/conversations", json={}, headers=headers)
    cid = created.json()["id"]
    provider = await http.post(
        "/models/providers",
        headers=headers,
        json={
            "kind": "openai_compatible",
            "display_name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "billed": True,
        },
    )
    assert provider.status_code == 200
    profiles = {item["role"]: item["id"] for item in provider.json()["profiles"]}
    assigned = await http.put("/models/assignments", headers=headers, json=profiles)
    assert assigned.status_code == 200
    response = await http.post(
        f"/conversations/{cid}/messages",
        json={"content": "What is add?"},
        headers=headers,
    )
    assert response.status_code == 409
    assert "Models page" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_secret_store_error_on_chat_is_conflict(tmp_path: Path) -> None:
    class _BoomStore:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def put(self, name: str, value: str) -> None:
            self.values[name] = value

        def get(self, name: str) -> str | None:
            raise SecretStoreError("OS credential storage could not read the secret")

        def delete(self, name: str) -> None:
            self.values.pop(name, None)

    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=_BoomStore())
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        root = init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
        repo_id = await _enrol(http, headers, root)
        created = await http.post(
            f"/repositories/{repo_id}/conversations", json={}, headers=headers
        )
        cid = created.json()["id"]
        provider = await http.post(
            "/models/providers",
            headers=headers,
            json={
                "kind": "openai_compatible",
                "display_name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "billed": True,
                "api_key": "sk-paid",
            },
        )
        assert provider.status_code == 200
        profiles = {item["role"]: item["id"] for item in provider.json()["profiles"]}
        assigned = await http.put("/models/assignments", headers=headers, json=profiles)
        assert assigned.status_code == 200
        response = await http.post(
            f"/conversations/{cid}/messages",
            json={"content": "What is add?"},
            headers=headers,
        )
        assert response.status_code == 409
        assert "Models page" in str(response.json()["detail"])
    finally:
        await http.aclose()


async def _read_sse(response: object) -> dict[str, object]:
    text_chunks: list[str] = []
    aiter_lines = getattr(response, "aiter_lines")
    async for line in aiter_lines():
        text_chunks.append(line)
    final: dict[str, object] | None = None
    for line in text_chunks:
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        parsed: object = json.loads(raw)
        if isinstance(parsed, dict) and (
            "goal_refs" in parsed or parsed.get("done") is True or parsed.get("event") == "final"
        ):
            final = parsed
    assert final is not None
    return final


def _scripted(replies: list[str]):
    remaining = list(replies)

    def complete(request: CompletionRequest, secret: object) -> CompletionResult:
        _ = request, secret
        return CompletionResult(text=remaining.pop(0), usage=TokenUsage(tokens=3))

    return complete


async def _assign_orchestrator(http: AsyncClient, headers: dict[str, str]) -> None:
    provider = await http.post(
        "/models/providers",
        headers=headers,
        json={
            "kind": "openai_compatible",
            "display_name": "Local",
            "base_url": "http://127.0.0.1:11434/v1",
            "billed": False,
            "api_key": "sk-chat",
        },
    )
    assert provider.status_code == 200
    profiles = {item["role"]: item["id"] for item in provider.json()["profiles"]}
    assigned = await http.put("/models/assignments", headers=headers, json=profiles)
    assert assigned.status_code == 200


async def _read_all_sse(response: object) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    aiter_lines = getattr(response, "aiter_lines")
    async for line in aiter_lines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        parsed: object = json.loads(raw)
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


@pytest.mark.asyncio
async def test_sse_tool_running_then_ok_then_deltas_then_done(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(
        _settings(tmp_path),
        database,
        secret_store=InMemorySecretStore(),
        chat_complete=_scripted(
            [
                '```tool\n{"name": "list_goals"}\n```',
                "No goals yet.",
            ]
        ),
    )
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        created = await http.post("/conversations", json={"repository_id": None}, headers=headers)
        assert created.status_code == 200
        cid = created.json()["id"]
        assert created.json()["repository_id"] is None
        await _assign_orchestrator(http, headers)
        async with http.stream(
            "POST",
            f"/conversations/{cid}/messages",
            json={"content": "list them"},
            headers=headers,
        ) as response:
            assert response.status_code == 200
            events = await _read_all_sse(response)
        kinds = []
        for item in events:
            if "tool" in item:
                tool = item["tool"]
                assert isinstance(tool, dict)
                kinds.append(("tool", str(tool.get("status"))))
            elif "delta" in item:
                kinds.append(("delta",))
            elif item.get("done") is True:
                kinds.append(("done",))
            elif "goal" in item:
                kinds.append(("goal",))
            elif "error" in item:
                kinds.append(("error",))
        assert kinds[0] == ("tool", "running")
        assert kinds[1] == ("tool", "ok")
        assert ("delta",) in kinds
        assert kinds[-1] == ("done",)
        assert kinds.index(("tool", "running")) < kinds.index(("tool", "ok"))
        assert kinds.index(("tool", "ok")) < kinds.index(("delta",))
        assert kinds.index(("delta",)) < kinds.index(("done",))
        detail = await http.get(f"/conversations/{cid}", headers=headers)
        assert detail.status_code == 200
        roles = [item["role"] for item in detail.json()["messages"]]
        assert "tool" in roles
        tool = next(item for item in detail.json()["messages"] if item["role"] == "tool")
        assert tool["tool_name"] == "list_goals"
        assert tool["tool_status"] == "ok"
        assert tool["tool_json"]
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_cancel_route_and_unauth(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    root = init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
    repo_id = await _enrol(http, headers, root)
    created = await http.post(f"/repositories/{repo_id}/conversations", json={}, headers=headers)
    cid = created.json()["id"]
    unauth = await http.post(f"/conversations/{cid}/cancel")
    assert unauth.status_code == 401
    cancelled = await http.post(f"/conversations/{cid}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["ok"] is True


@pytest.mark.asyncio
async def test_null_repository_conversation_and_auth(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, _tmp_path = client
    unauth = await http.get("/conversations")
    assert unauth.status_code == 401
    created = await http.post(
        "/conversations", json={"repository_id": None, "title": "Loose"}, headers=headers
    )
    assert created.status_code == 200
    assert created.json()["repository_id"] is None
    listed = await http.get("/conversations", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == created.json()["id"] for item in listed.json()["conversations"])
    missing = await http.get("/conversations/conv_missing/images/img_x", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_chat_images_route_round_trip(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(
        _settings(tmp_path),
        database,
        secret_store=InMemorySecretStore(),
        chat_complete=_scripted(["That is a screenshot."]),
    )
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        created = await http.post("/conversations", json={}, headers=headers)
        cid = created.json()["id"]
        unauth = await http.get(f"/conversations/{cid}/images/img_missing")
        assert unauth.status_code == 401
        empty = await http.post(
            f"/conversations/{cid}/messages",
            json={"content": "  "},
            headers=headers,
        )
        assert empty.status_code == 400
        await _assign_orchestrator(http, headers)
        async with http.stream(
            "POST",
            f"/conversations/{cid}/messages",
            json={
                "content": "What is this?",
                "images": [{"mime": "image/png", "data": TINY_PNG_B64}],
            },
            headers=headers,
        ) as response:
            assert response.status_code == 200
            await _read_sse(response)
        detail = await http.get(f"/conversations/{cid}", headers=headers)
        user = next(item for item in detail.json()["messages"] if item["role"] == "user")
        assert "kronos-image:" in user["content"]
        image_id = user["content"].split("kronos-image:")[1].rstrip(")")
        loaded = await http.get(f"/conversations/{cid}/images/{image_id}", headers=headers)
        assert loaded.status_code == 200
        assert loaded.json()["mime"] == "image/png"
        assert loaded.json()["data"] == TINY_PNG_B64
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_goal_readiness_route(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    unauth_missing = await http.get("/repositories/repo_x/goal-readiness")
    assert unauth_missing.status_code == 401
    root = init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
    repo_id = await _enrol(http, headers, root)
    missing = await http.get("/repositories/repo_missing/goal-readiness", headers=headers)
    assert missing.status_code == 404
    ready = await http.get(f"/repositories/{repo_id}/goal-readiness", headers=headers)
    assert ready.status_code == 200
    body = ready.json()
    assert "can_execute" in body
    ids = [item["id"] for item in body["checks"]]
    assert ids[0] == "workspace_active"
    assert "models_assigned" in ids
    assert "budget" in ids
