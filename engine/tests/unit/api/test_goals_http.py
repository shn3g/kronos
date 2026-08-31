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
async def test_goals_and_runs_http_create_and_list(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    repo = init_git_repo(
        tmp_path / "alpha",
        origin="https://github.com/acme/alpha.git",
        files={"README.md": "alpha\n"},
    )
    enrolled = await http.post("/repositories", json={"path": str(repo)}, headers=headers)
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    created = await http.post(
        "/goals",
        json={
            "repository_id": repo_id,
            "title": "Fix add",
            "success_criteria": "add returns a+b",
            "non_goals": "rewrite packaging",
            "risk_ceiling": "low",
            "source": "desktop",
            "max_attempts": 3,
        },
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["title"] == "Fix add"
    assert body["state"] == "draft"
    assert body["repository_id"] == repo_id

    listed = await http.get("/goals", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["goals"]) == 1
    assert listed.json()["goals"][0]["id"] == body["id"]

    detail = await http.get(f"/goals/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["goal"]["id"] == body["id"]
    assert detail.json()["tasks"] == []

    runs = await http.get("/runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json() == {"runs": []}


@pytest.mark.asyncio
async def test_create_goal_rejects_missing_criteria(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    repo = init_git_repo(tmp_path / "alpha", origin="https://github.com/acme/alpha.git")
    enrolled = await http.post("/repositories", json={"path": str(repo)}, headers=headers)
    repo_id = enrolled.json()["repository"]["id"]
    response = await http.post(
        "/goals",
        json={
            "repository_id": repo_id,
            "title": "Fix add",
            "success_criteria": "",
            "non_goals": "scope",
            "risk_ceiling": "low",
            "source": "api",
            "max_attempts": 3,
        },
        headers=headers,
    )
    assert response.status_code == 400


POLICY_LIVE = {
    "schema_version": 2,
    "branches": {"integration": "integration", "protected": "main"},
    "commands": {
        "setup": [],
        "test": ["python", "-c", "raise SystemExit(1)"],
        "lint": [],
        "build": [],
    },
    "autonomy": {"freeze": False, "invent_issues": False, "refill_enabled": False},
    "paths": {"locked_prefixes": []},
    "risk": {"floor": "low"},
    "budgets": {
        "max_attempts_per_issue": 3,
        "max_dispatches_per_day": 12,
        "breaker_failure_limit": 4,
        "dry_run_meters": False,
    },
    "wip": {"ready": 2, "running": 3},
    "executor": {"profile": "standard", "sandbox": "default"},
    "indexing": {"enabled": True, "exclude_prefixes": ["node_modules/"], "max_file_bytes": 1048576},
}


@pytest.mark.asyncio
async def test_plan_and_tick_run_outside_pytest_harness(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    repo = init_git_repo(
        tmp_path / "alpha",
        origin="https://github.com/acme/alpha.git",
        files={"pkg/math.py": "def add(a, b):\n    return a\n", "pkg/__init__.py": ""},
    )
    enrolled = await http.post(
        "/repositories", json={"path": str(repo), "policy": POLICY_LIVE}, headers=headers
    )
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]
    rebuilt = await http.post(f"/repositories/{repo_id}/index/rebuild", headers=headers)
    assert rebuilt.status_code == 200

    created = await http.post(
        "/goals",
        json={
            "repository_id": repo_id,
            "title": "Fix add",
            "success_criteria": "add returns a+b",
            "non_goals": "rewrite packaging",
            "risk_ceiling": "low",
            "source": "desktop",
            "max_attempts": 3,
        },
        headers=headers,
    )
    assert created.status_code == 200
    goal_id = created.json()["id"]
    assert created.json()["state"] == "draft"
    assert created.json()["max_attempts"] == 3

    planned = await http.post(f"/goals/{goal_id}/plan", headers=headers)
    assert planned.status_code == 200
    assert planned.json()["goal"]["state"] == "planned"
    assert planned.json()["tasks"]

    events = await http.get("/events", headers=headers)
    assert events.status_code == 200
    types = [item["type"] for item in events.json()["events"]]
    assert "goal.transitioned" in types

    ticked = await http.post("/goals/tick", headers=headers)
    assert ticked.status_code == 200
    body = ticked.json()
    assert body["status"] != "idle"
    later = await http.get("/events", headers=headers)
    later_types = [item["type"] for item in later.json()["events"]]
    assert "task.transitioned" in later_types or "task.claimed" in later_types


@pytest.mark.asyncio
async def test_ingest_github_refuses_empty_nongoals(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, tmp_path = client
    repo = init_git_repo(tmp_path / "alpha", origin="https://github.com/acme/alpha.git")
    enrolled = await http.post("/repositories", json={"path": str(repo)}, headers=headers)
    repo_id = enrolled.json()["repository"]["id"]
    response = await http.post(
        "/goals/ingest",
        json={
            "source": "github_issue",
            "repository_id": repo_id,
            "title": "From GitHub",
            "body": "do the thing",
            "non_goals": "",
            "risk_ceiling": "medium",
            "max_attempts": 3,
        },
        headers=headers,
    )
    assert response.status_code == 400
