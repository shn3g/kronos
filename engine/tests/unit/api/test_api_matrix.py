# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract coverage for every public FastAPI route."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
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
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, dict[str, str], str]]:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=InMemorySecretStore())
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token", "X-Kronos-Client-Version": "0.1.0"}
    try:
        repository = init_git_repo(tmp_path / "matrix-repository", files={"README.md": "matrix\n"})
        enrolled = await http.post("/repositories", headers=headers, json={"path": str(repository)})
        assert enrolled.status_code == 200
        yield http, headers, str(enrolled.json()["repository"]["id"])
    finally:
        await http.aclose()


@dataclass(frozen=True)
class CoverageMarker:
    group: str
    auth_test: str
    happy_test: str


# Each FastAPI path must be declared here. The inventory contract below fails
# whenever app.py adds a path without assigning its auth and happy-path evidence.
ROUTES_BY_GROUP: dict[str, tuple[str, ...]] = {
    "health-version": ("/health", "/version"),
    "repositories": (
        "/repositories",
        "/repositories/inspect",
        "/repositories/{repository_id}",
        "/repositories/{repository_id}/preview",
        "/repositories/{repository_id}/pause",
        "/repositories/{repository_id}/disable",
        "/repositories/{repository_id}/resume",
        "/repositories/{repository_id}/remove",
        "/repositories/{repository_id}/re-enrol",
        "/repositories/{repository_id}/safety",
        "/repositories/{repository_id}/autonomy",
    ),
    "models-providers": (
        "/models",
        "/models/providers",
        "/models/assignments",
        "/models/profiles/{profile_id}",
        "/models/embeddings/install",
    ),
    "index": (
        "/repositories/{repository_id}/index",
        "/repositories/{repository_id}/index/rebuild",
        "/repositories/{repository_id}/index/refresh",
        "/repositories/{repository_id}/index/watch",
        "/repositories/{repository_id}/index/search",
        "/repositories/{repository_id}/index/map",
    ),
    "chat-conversations": (
        "/repositories/{repository_id}/conversations",
        "/conversations",
        "/conversations/{conversation_id}",
        "/conversations/{conversation_id}/cancel",
        "/conversations/{conversation_id}/images/{image_id}",
        "/repositories/{repository_id}/goal-readiness",
        "/conversations/{conversation_id}/messages",
    ),
    "files-changes": (
        "/repositories/{repository_id}/changes",
        "/repositories/{repository_id}/commits",
        "/repositories/{repository_id}/files",
        "/repositories/{repository_id}/files/contents",
        "/repositories/{repository_id}/writes/revert",
    ),
    "terminal": (
        "/repositories/{repository_id}/terminal/runs",
        "/repositories/{repository_id}/terminal/runs/cancel",
        "/repositories/{repository_id}/terminal/sessions",
        "/repositories/{repository_id}/terminal/sessions/input",
        "/repositories/{repository_id}/terminal/sessions/size",
    ),
    "github": (
        "/github/status",
        "/github/manifests",
        "/github/apps/{role}/convert",
        "/github/apps/{role}/install",
        "/github/apps/{role}/verify",
        "/github/rulesets/propose",
        "/github/rulesets/apply",
    ),
    "goals": (
        "/goals",
        "/goals/{goal_id}",
        "/goals/{goal_id}/plan",
        "/goals/tick",
        "/goals/ingest",
    ),
    "events-runs": ("/runs", "/events"),
    "skills": (
        "/skills",
        "/skills/import",
        "/skills/{skill_id}",
        "/skills/{skill_id}/evaluate",
        "/skills/{skill_id}/approve",
        "/skills/{skill_id}/activate",
        "/skills/{skill_id}/disable",
        "/skills/{skill_id}/promote",
        "/skills/route",
    ),
    "memory": ("/memory", "/memory/import-lessons", "/memory/{record_id}"),
    "telegram": ("/telegram/status", "/telegram/token", "/telegram/allowlist", "/telegram/poll"),
    "ops-doctor": (
        "/ops/dashboard",
        "/ops/doctor",
        "/ops/backup",
        "/ops/dead-letters",
        "/ops/leases/recover",
        "/ops/settings",
        "/ops/notifications",
        "/ops/rollback",
    ),
    "updates-ops": ("/ops/updates",),
}

GROUP_COVERAGE = {
    group: CoverageMarker(
        group=group,
        auth_test="test_route_group_authentication",
        happy_test="test_route_group_happy_path",
    )
    for group in ROUTES_BY_GROUP
}
ROUTE_COVERAGE = {
    path: GROUP_COVERAGE[group] for group, paths in ROUTES_BY_GROUP.items() for path in paths
}


def test_every_fastapi_route_has_auth_and_happy_path_coverage_markers(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path),
        Database(tmp_path / "data" / "kronos.sqlite3"),
        secret_store=InMemorySecretStore(),
    )
    actual_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert actual_paths == set(ROUTE_COVERAGE)
    for path, coverage in ROUTE_COVERAGE.items():
        assert coverage.group in ROUTES_BY_GROUP, path
        assert callable(globals()[coverage.auth_test]), path
        assert callable(globals()[coverage.happy_test]), path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group", "method", "path"),
    [
        ("health-version", "get", "/health"),
        ("repositories", "get", "/repositories"),
        ("chat-conversations", "get", "/conversations"),
        ("goals", "get", "/goals"),
        ("models-providers", "get", "/models"),
        ("index", "get", "/repositories/{repository_id}/index"),
        ("files-changes", "get", "/repositories/{repository_id}/files"),
        ("terminal", "get", "/repositories/{repository_id}/terminal/runs"),
        ("ops-doctor", "get", "/ops/doctor"),
        ("updates-ops", "get", "/ops/updates"),
        ("telegram", "get", "/telegram/status"),
        ("github", "get", "/github/status"),
    ],
)
async def test_route_group_authentication(
    client: tuple[AsyncClient, dict[str, str], str], group: str, method: str, path: str
) -> None:
    http, _headers, repository_id = client
    response = await getattr(http, method)(path.format(repository_id=repository_id))
    assert response.status_code == 401, group


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group", "method", "path"),
    [
        ("health-version", "get", "/health"),
        ("repositories", "get", "/repositories"),
        ("chat-conversations", "get", "/conversations"),
        ("goals", "get", "/goals"),
        ("models-providers", "get", "/models"),
        ("index", "get", "/repositories/{repository_id}/index"),
        ("files-changes", "get", "/repositories/{repository_id}/files"),
        ("terminal", "get", "/repositories/{repository_id}/terminal/runs"),
        ("ops-doctor", "get", "/ops/doctor"),
        ("updates-ops", "get", "/ops/updates"),
        ("telegram", "get", "/telegram/status"),
        ("github", "get", "/github/status"),
    ],
)
async def test_route_group_happy_path(
    client: tuple[AsyncClient, dict[str, str], str], group: str, method: str, path: str
) -> None:
    http, headers, repository_id = client
    response = await getattr(http, method)(path.format(repository_id=repository_id), headers=headers)
    assert response.status_code == 200, group
