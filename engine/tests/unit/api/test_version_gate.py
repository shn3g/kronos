# SPDX-License-Identifier: AGPL-3.0-or-later

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.state.database import Database


@pytest.fixture
async def http(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    settings = Settings(
        engine_version="0.1.0",
        min_client_version="0.1.0",
        bind_host="127.0.0.1",
        bind_port=0,
        auth_token="install-token",
        paths=paths,
    )
    database = Database(tmp_path / "kronos.sqlite3")
    client = AsyncClient(
        transport=ASGITransport(app=create_app(settings, database), client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer install-token"},
    )
    try:
        yield client
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_incompatible_desktop_version_is_reported(http: AsyncClient) -> None:
    response = await http.get("/version", headers={"X-Kronos-Client-Version": "0.0.1"})
    assert response.status_code == 200
    body = response.json()
    assert body["compatible"] is False
    assert body["engine_version"] == "0.1.0"


@pytest.mark.asyncio
async def test_newer_desktop_is_incompatible_with_older_engine(http: AsyncClient) -> None:
    response = await http.get("/version", headers={"X-Kronos-Client-Version": "0.2.0"})
    assert response.status_code == 200
    assert response.json()["compatible"] is False


@pytest.mark.asyncio
async def test_missing_client_version_is_incompatible(http: AsyncClient) -> None:
    response = await http.get("/version")
    assert response.status_code == 200
    assert response.json()["compatible"] is False
