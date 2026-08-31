# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.retrieval.support import golden_fixture
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
async def test_index_http_rebuild_search_and_isolation(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    alpha = golden_fixture(tmp_path / "alpha")
    beta = init_git_repo(
        tmp_path / "beta",
        files={"src/beta.py": "BETA_ONLY_TOKEN = 1\n"},
    )
    enrolled_alpha = await http.post("/repositories", headers=headers, json={"path": str(alpha)})
    enrolled_beta = await http.post("/repositories", headers=headers, json={"path": str(beta)})
    assert enrolled_alpha.status_code == 200
    assert enrolled_beta.status_code == 200
    alpha_id = enrolled_alpha.json()["repository"]["id"]
    beta_id = enrolled_beta.json()["repository"]["id"]

    unauth = await http.post(f"/repositories/{alpha_id}/index/rebuild")
    assert unauth.status_code == 401

    rebuilt = await http.post(f"/repositories/{alpha_id}/index/rebuild", headers=headers)
    assert rebuilt.status_code == 200
    status = rebuilt.json()
    assert status["repository_id"] == alpha_id
    assert status["chunk_count"] > 0
    assert "indexes" in status["index_path"].replace("\\", "/")
    assert alpha_id in status["index_path"]
    assert Path(alpha).resolve() not in Path(status["index_path"]).resolve().parents

    search = await http.get(
        f"/repositories/{alpha_id}/index/search",
        headers=headers,
        params={"q": "connect"},
    )
    assert search.status_code == 200
    items = search.json()["items"]
    assert items
    first = items[0]
    assert first["path"]
    assert first["commit"]
    assert first["rank_sources"]
    assert first["trust"]
    blob = "\n".join(item["text"] for item in items)
    assert "AKIAIOSFODNN7EXAMPLE" not in blob
    assert not any(item["path"].endswith("secrets.env") for item in items)

    leaked = await http.get(
        f"/repositories/{alpha_id}/index/search",
        headers=headers,
        params={"q": "BETA_ONLY_TOKEN"},
    )
    assert leaked.json()["items"] == []

    missing = await http.get("/repositories/repo_missing/index", headers=headers)
    assert missing.status_code == 404

    await http.post(f"/repositories/{beta_id}/index/rebuild", headers=headers)
    beta_search = await http.get(
        f"/repositories/{beta_id}/index/search",
        headers=headers,
        params={"q": "BETA_ONLY_TOKEN"},
    )
    assert any("beta.py" in item["path"] for item in beta_search.json()["items"])
    mapped = await http.get(f"/repositories/{alpha_id}/index/map", headers=headers)
    assert mapped.status_code == 200
    assert mapped.json()["text"]
