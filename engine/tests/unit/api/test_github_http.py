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
        "/github/apps/controller/convert",
        headers=headers,
        json={"code": "controller-manifest"},
    )
    assert created.status_code == 200
    assert "BEGIN RSA" not in str(created.json())
    db_bytes = (tmp_path / "data" / "kronos.sqlite3").read_bytes()
    assert b"BEGIN RSA PRIVATE KEY" not in db_bytes

    tokenish = await http.post(
        "/github/apps/controller/convert",
        headers=headers,
        json={"code": "", "gh_token": "ghp_nope"},
    )
    assert tokenish.status_code == 400


@pytest.mark.asyncio
async def test_manifest_convert_stores_pem_and_status_includes_enrolled_origin(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    converted = await http.post(
        "/github/apps/controller/convert",
        headers=headers,
        json={"code": "controller-manifest"},
    )
    assert converted.status_code == 200
    body = converted.json()
    assert "BEGIN RSA" not in str(body)
    assert "private_key" not in str(body)
    assert body["role"] == "controller"
    assert body["app_id"] == 1001
    assert body["slug"] == "kronos-controller"
    db_bytes = (tmp_path / "data" / "kronos.sqlite3").read_bytes()
    assert b"BEGIN RSA PRIVATE KEY" not in db_bytes

    pem_rejected = await http.post(
        "/github/apps/controller",
        headers=headers,
        json={
            "app_id": 1001,
            "slug": "kronos-controller",
            "private_key": TEST_CONTROLLER_PEM,
        },
    )
    assert pem_rejected.status_code in {404, 405, 422}

    from tests.support.git_fixtures import init_git_repo

    repo = init_git_repo(
        tmp_path / "shop",
        origin="https://github.com/widgets/shop.git",
        files={"README.md": "shop\n"},
    )
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    status = await http.get("/github/status", headers=headers)
    assert status.status_code == 200
    payload = status.json()
    assert payload["enrolled"]["owner"] == "widgets"
    assert payload["enrolled"]["repo"] == "shop"
    assert payload["controller"]["app_id"] == 1001
    assert payload["controller"]["slug"] == "kronos-controller"
    assert "settings/apps/new" in payload["controller"]["create_url"]
    assert payload["controller"]["registered"] is True


@pytest.mark.asyncio
async def test_ruleset_apply_uses_request_owner_and_repo(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, _tmp_path = client
    await http.post(
        "/github/apps/controller/convert",
        headers=headers,
        json={"code": "controller-manifest"},
    )
    await http.post(
        "/github/apps/controller/install",
        headers=headers,
        json={"installation_id": 2001},
    )
    await http.post("/github/apps/controller/verify", headers=headers)
    applied = await http.post(
        "/github/rulesets/apply",
        headers=headers,
        json={
            "owner": "acme",
            "repo": "app",
            "reviewer_integration_id": 1002,
            "confirm": True,
        },
    )
    assert applied.status_code == 200
    missing = await http.post(
        "/github/rulesets/apply",
        headers=headers,
        json={
            "owner": "other",
            "repo": "missing",
            "reviewer_integration_id": 1002,
            "confirm": True,
        },
    )
    assert missing.status_code >= 400
