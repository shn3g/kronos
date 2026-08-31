# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.git_fixtures import init_git_repo

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
    app = create_app(_settings(tmp_path), database)
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    try:
        yield http, {"Authorization": "Bearer install-token"}, tmp_path
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_goals_and_runs_http_create_and_list(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    repo = init_git_repo(
        tmp_path / "alpha",
        origin="https://github.com/acme/alpha.git",
        files={"README.md": "alpha\n"},
    )
    enrolled = await http.post("/repositories", json={"path": str(repo)}, headers=headers)
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    created = await http.post(
        "/goals",
        json={
            "repository_id": repo_id,
            "title": "Fix add",
            "success_criteria": "add returns a+b",
            "non_goals": "rewrite packaging",
            "risk_ceiling": "low",
            "source": "desktop",
        },
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["title"] == "Fix add"
    assert body["state"] == "draft"
    assert body["repository_id"] == repo_id

    listed = await http.get("/goals", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["goals"]) == 1
    assert listed.json()["goals"][0]["id"] == body["id"]

    detail = await http.get(f"/goals/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["goal"]["id"] == body["id"]
    assert detail.json()["tasks"] == []

    runs = await http.get("/runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json() == {"runs": []}


@pytest.mark.asyncio
async def test_create_goal_rejects_missing_criteria(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    repo = init_git_repo(tmp_path / "alpha", origin="https://github.com/acme/alpha.git")
    enrolled = await http.post("/repositories", json={"path": str(repo)}, headers=headers)
    repo_id = enrolled.json()["repository"]["id"]
    response = await http.post(
        "/goals",
        json={
            "repository_id": repo_id,
            "title": "Fix add",
            "success_criteria": "",
            "non_goals": "scope",
            "risk_ceiling": "low",
            "source": "api",
        },
        headers=headers,
    )
    assert response.status_code == 400
