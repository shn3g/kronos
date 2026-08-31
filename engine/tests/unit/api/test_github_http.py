# SPDX-License-Identifier: AGPL-3.0-or-later
"""GitHub HTTP surface: fail-closed auth, no secrets in responses, composition only."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.github_fixture import TEST_CONTROLLER_PEM, GitHubFixture
from tests.support.secrets import InMemorySecretStore

from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
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
    secrets = InMemorySecretStore()
    fixture = GitHubFixture()
    app = create_app(
        _settings(tmp_path),
        database,
        secret_store=secrets,
        github_transport=fixture,
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
async def test_github_status_requires_auth_and_hides_secrets(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    unauth = await http.get("/github/status")
    assert unauth.status_code == 401

    status = await http.get("/github/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["webhook_enabled"] is False
    assert body["poll_mode"] == "conditional"
    assert "private_key" not in str(body)
    assert "token" not in str(body).lower() or "installation_token" not in str(body)

    manifests = await http.get("/github/manifests", headers=headers)
    assert manifests.status_code == 200
    payload = manifests.json()
    assert payload["controller"]["name"]
    assert payload["reviewer"]["name"]
    assert KRONOS_REVIEW_CHECK_NAME in payload["reviewer_check_name"]

    created = await http.post(
        "/github/apps/controller",
        headers=headers,
        json={
            "app_id": 1001,
            "slug": "kronos-controller",
            "private_key": TEST_CONTROLLER_PEM,
        },
    )
    assert created.status_code == 200
    assert "BEGIN RSA" not in str(created.json())
    db_bytes = (tmp_path / "data" / "kronos.sqlite3").read_bytes()
    assert b"BEGIN RSA PRIVATE KEY" not in db_bytes

    tokenish = await http.post(
        "/github/apps/controller",
        headers=headers,
        json={"app_id": 1, "slug": "x", "private_key": "", "gh_token": "ghp_nope"},
    )
    assert tokenish.status_code == 400
