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
async def test_enrolment_endpoints_list_isolate_and_keep_preview_only(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    alpha = init_git_repo(
        tmp_path / "alpha",
        origin="https://github.com/acme/alpha.git",
        files={"README.md": "alpha\n", "pyproject.toml": "[project]\nname='alpha'\n"},
    )
    beta = init_git_repo(
        tmp_path / "beta",
        origin="https://github.com/acme/beta.git",
        files={"README.md": "beta\n"},
    )

    missing = await http.post("/repositories/inspect", headers=headers)
    assert missing.status_code == 401 or missing.status_code == 422
    unauth = await http.post("/repositories/inspect", json={"path": str(alpha)})
    assert unauth.status_code == 401

    inspected = await http.post(
        "/repositories/inspect", headers=headers, json={"path": str(alpha)}
    )
    assert inspected.status_code == 200
    body = inspected.json()
    assert body["wrote_files"] is False
    assert body["committed"] is False
    assert body["pushed"] is False
    assert not (alpha / ".kronos").exists()

    first = await http.post("/repositories", headers=headers, json={"path": str(alpha)})
    second = await http.post(
        "/repositories",
        headers=headers,
        json={"path": str(beta), "policy": {"autonomy": {"freeze": False}}},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    alpha_id = first.json()["repository"]["id"]
    beta_id = second.json()["repository"]["id"]
    assert alpha_id != beta_id

    listed = await http.get("/repositories", headers=headers)
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["repositories"]}
    assert ids == {alpha_id, beta_id}

    alpha_get = await http.get(f"/repositories/{alpha_id}", headers=headers)
    beta_get = await http.get(f"/repositories/{beta_id}", headers=headers)
    assert alpha_get.status_code == 200
    assert beta_get.status_code == 200
    assert alpha_get.json()["policy"]["autonomy"]["freeze"] is True
    assert beta_get.json()["policy"]["autonomy"]["freeze"] is False
    assert alpha_get.json()["repository"]["id"] != beta_get.json()["repository"]["id"]

    missing_id = await http.get("/repositories/repo_not-a-real-id", headers=headers)
    assert missing_id.status_code == 404
    assert "freeze" not in missing_id.text

    paused = await http.post(f"/repositories/{alpha_id}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["repository"]["status"] == "paused"
    disabled = await http.post(f"/repositories/{beta_id}/disable", headers=headers)
    assert disabled.json()["repository"]["status"] == "disabled"

    preview = await http.get(f"/repositories/{alpha_id}/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["wrote_files"] is False
    stored_preview = await http.get(f"/repositories/{beta_id}/preview", headers=headers)
    assert stored_preview.status_code == 200
    assert stored_preview.json()["policy"]["autonomy"]["freeze"] is False
    config = next(
        item["content"]
        for item in stored_preview.json()["preview"]
        if item["path"] == ".kronos/config.yaml"
    )
    assert "freeze: false" in config
    resumed = await http.post(f"/repositories/{alpha_id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["repository"]["status"] == "active"
    assert resumed.json()["policy"]["autonomy"]["freeze"] is True
    reenrolled = await http.post(f"/repositories/{beta_id}/re-enrol", headers=headers)
    assert reenrolled.status_code == 200
    assert reenrolled.json()["policy"]["autonomy"]["freeze"] is False
    assert not (alpha / ".kronos").exists()
    assert not (beta / ".kronos").exists()
