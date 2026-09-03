# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unexpected engine errors reach the desktop as plain JSON detail."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
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


@pytest.mark.asyncio
async def test_unhandled_exception_returns_json_detail(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=InMemorySecretStore())

    leaked_key = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"

    @app.get("/__boom")
    def boom() -> None:
        raise RuntimeError(f"{leaked_key} exploded")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://127.0.0.1",
    ) as http:
        response = await http.get("/__boom", headers={"Authorization": "Bearer install-token"})
    assert response.status_code == 500
    body = response.json()
    assert body["detail"].startswith("RuntimeError:")
    assert "exploded" in body["detail"]
    assert leaked_key not in body["detail"]


@pytest.mark.asyncio
async def test_unhandled_exception_detail_is_clipped(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=InMemorySecretStore())

    @app.get("/__long")
    def long_error() -> None:
        raise ValueError("x " * 1000)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://127.0.0.1",
    ) as http:
        response = await http.get("/__long", headers={"Authorization": "Bearer install-token"})
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail.startswith("ValueError:")
    assert len(detail) <= len("ValueError: ") + 300
