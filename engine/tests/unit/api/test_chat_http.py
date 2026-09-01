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

from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.state.database import Database


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
