# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.git_fixtures import init_git_repo
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
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=InMemorySecretStore())
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        yield http, headers, repo
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_working_tree_changes_and_commit_fail_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]
    (repo / "hello.py").write_text("new\n", encoding="utf-8")
    (repo / "fresh.py").write_text("hi\n", encoding="utf-8")

    unauth = await http.get(f"/repositories/{repo_id}/changes")
    assert unauth.status_code == 401

    listed = await http.get(f"/repositories/{repo_id}/changes", headers=headers)
    assert listed.status_code == 200
    paths = {item["path"]: item for item in listed.json()["changes"]}
    assert "-old" in paths["hello.py"]["patch"]
    assert "+new" in paths["hello.py"]["patch"]
    assert paths["fresh.py"]["summary"].startswith("Added")

    empty = await http.post(
        f"/repositories/{repo_id}/commits",
        headers=headers,
        json={"message": "   "},
    )
    assert empty.status_code == 400

    committed = await http.post(
        f"/repositories/{repo_id}/commits",
        headers=headers,
        json={"message": "Fix hello.py", "paths": ["hello.py", "fresh.py"]},
    )
    assert committed.status_code == 200
    assert committed.json()["ok"] is True
    assert (repo / "hello.py").read_text(encoding="utf-8") == "new\n"

    after = await http.get(f"/repositories/{repo_id}/changes", headers=headers)
    assert after.json()["changes"] == []

    nothing = await http.post(
        f"/repositories/{repo_id}/commits",
        headers=headers,
        json={"message": "Again"},
    )
    assert nothing.status_code == 409
