# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.domain.models import MODEL_ROLES
from kronos_engine.state.database import Database


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


class _QuietDetector:
    def detect(self) -> tuple[object, ...]:
        return ()


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, dict[str, str], Path]]:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, tool_detector=_QuietDetector())
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    try:
        yield http, {"Authorization": "Bearer install-token"}, tmp_path
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_models_endpoints_fail_closed_and_hide_secrets(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    unauth = await http.get("/models")
    assert unauth.status_code == 401

    listed = await http.get("/models", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert set(body["assignments"]) == set(MODEL_ROLES)
    assert "api_key" not in str(body)

    created = await http.post(
        "/models/providers",
        headers=headers,
        json={
            "kind": "openai_compatible",
            "display_name": "Ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "billed": False,
            "api_key": "sk-http-secret",
        },
    )
    assert created.status_code == 200
    created_body = created.json()
    assert "sk-http-secret" not in str(created_body)
    provider_id = created_body["provider"]["id"]
    profile_id = created_body["profile"]["id"]

    assigned = await http.put(
        "/models/assignments",
        headers=headers,
        json={role: profile_id for role in MODEL_ROLES},
    )
    assert assigned.status_code == 200
    snapshot = (await http.get("/models", headers=headers)).json()
    assert snapshot["assignments"]["planner"] == profile_id
    assert snapshot["assignments"]["coder"] == profile_id
    assert snapshot["assignments"]["reviewer"] == profile_id
    assert snapshot["assignments"]["embedding"] == profile_id
    assert snapshot["providers"][0]["id"] == provider_id
    assert "sk-http-secret" not in str(snapshot)
    db_bytes = (tmp_path / "data" / "kronos.sqlite3").read_bytes()
    assert b"sk-http-secret" not in db_bytes

    missing = await http.put("/models/assignments", headers=headers, json={"planner": profile_id})
    assert missing.status_code == 400
