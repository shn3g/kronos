# SPDX-License-Identifier: AGPL-3.0-or-later

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.state.database import connect


def _settings(tmp_path: Path, token: str = "install-token") -> Settings:
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
        auth_token=token,
        paths=paths,
    )


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    conn = connect(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), conn)
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    try:
        yield http, {"Authorization": "Bearer install-token"}
    finally:
        await http.aclose()
        conn.close()


def test_settings_reject_non_loopback_bind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(
            engine_version="0.1.0",
            min_client_version="0.1.0",
            bind_host="0.0.0.0",
            bind_port=8080,
            auth_token="x",
            paths=_settings(tmp_path).paths,
        )


@pytest.mark.asyncio
async def test_wrong_token_is_401(client: tuple[AsyncClient, dict[str, str]]) -> None:
    http, _ = client
    response = await http.get("/health", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_is_401(client: tuple[AsyncClient, dict[str, str]]) -> None:
    http, _ = client
    response = await http.get("/repositories")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_version_catalog_and_events(
    client: tuple[AsyncClient, dict[str, str]],
) -> None:
    http, headers = client
    health = await http.get("/health", headers=headers)
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    version = await http.get("/version", headers={**headers, "X-Kronos-Client-Version": "0.1.0"})
    assert version.status_code == 200
    body = version.json()
    assert body["engine_version"] == "0.1.0"
    assert body["compatible"] is True

    repos = await http.get("/repositories", headers=headers)
    assert repos.status_code == 200
    assert repos.json() == {"repositories": []}

    goals = await http.get("/goals", headers=headers)
    assert goals.status_code == 200
    assert goals.json() == {"goals": []}

    events = await http.get("/events", headers=headers)
    assert events.status_code == 200
    assert events.json() == {"events": [], "head_seq": 0}
