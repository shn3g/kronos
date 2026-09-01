# SPDX-License-Identifier: AGPL-3.0-or-later
"""Safety GET and autonomy POST go through RepositoryService, not raw SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.git_fixtures import init_git_repo
from tests.support.github_fixture import GitHubFixture
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
    app = create_app(
        _settings(tmp_path),
        database,
        secret_store=InMemorySecretStore(),
        github_transport=GitHubFixture(),
    )
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    try:
        yield http, {"Authorization": "Bearer install-token"}, tmp_path
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_safety_get_and_elevation_refused_without_protection(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    repo = init_git_repo(
        tmp_path / "shop",
        origin="https://github.com/widgets/shop.git",
        files={"README.md": "shop\n"},
    )
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    unauth = await http.get(f"/repositories/{repo_id}/safety")
    assert unauth.status_code == 401

    safety = await http.get(f"/repositories/{repo_id}/safety", headers=headers)
    assert safety.status_code == 200
    body = safety.json()
    assert body["ok"] is False
    check_ids = {item["id"] for item in body["checks"]}
    assert check_ids == {"ruleset_strict", "kronos_pr_workflow", "codeowners", "reviewer_app"}
    assert all("ok" in item and "detail" in item for item in body["checks"])
    assert any(item["id"] == "ruleset_strict" and item["ok"] is False for item in body["checks"])
    assert any(item["id"] == "reviewer_app" and item["ok"] is False for item in body["checks"])

    refused = await http.post(
        f"/repositories/{repo_id}/autonomy",
        headers=headers,
        json={"mode": "write_draft_prs"},
    )
    assert refused.status_code == 409

    issues = await http.post(
        f"/repositories/{repo_id}/autonomy",
        headers=headers,
        json={"mode": "write_issues", "freeze": False},
    )
    assert issues.status_code == 200
    assert issues.json()["policy"]["autonomy"]["mode"] == "write_issues"
    assert issues.json()["policy"]["autonomy"]["freeze"] is False
