# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ops HTTP: dashboard, doctor, backup, dead letters, settings. No secrets."""

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

PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEAfakeprivatekeymaterialforredactiontestxx\n"
    "-----END RSA PRIVATE KEY-----"
)
BOT = "123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


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
async def client(
    tmp_path: Path,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str], Path, InMemorySecretStore]]:
    secrets = InMemorySecretStore()
    secrets.put("telegram:bot_token", BOT)
    secrets.put("github:controller:private_key", PEM)
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=secrets)
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {
        "Authorization": "Bearer install-token",
        "X-Kronos-Client-Version": "0.1.0",
    }
    try:
        yield http, headers, tmp_path, secrets
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_dashboard_surfaces_schedules_budgets_runs_and_index(
    client: tuple[AsyncClient, dict[str, str], Path, InMemorySecretStore],
) -> None:
    http, headers, tmp_path, _secrets = client
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
            "title": "Nightly scan",
            "success_criteria": "tests pass",
            "non_goals": "rewrite",
            "risk_ceiling": "low",
            "source": "desktop",
            "schedule": "0 4 * * *",
            "max_attempts": 3,
        },
        headers=headers,
    )
    assert created.status_code == 200
    dash = await http.get("/ops/dashboard", headers=headers)
    assert dash.status_code == 200
    body = dash.json()
    assert body["ready"] is True
    assert any(item["id"] == repo_id for item in body["repositories"])
    assert any(item["title"] == "Nightly scan" for item in body["schedules"])
    assert "budgets" in body
    assert "runs" in body
    assert "diffs" in body
    assert "tests" in body
    assert "index" in body
    encoded = str(body)
    assert BOT not in encoded
    assert "BEGIN RSA" not in encoded


@pytest.mark.asyncio
async def test_doctor_backup_dead_letters_and_settings_hide_secrets(
    client: tuple[AsyncClient, dict[str, str], Path, InMemorySecretStore],
) -> None:
    http, headers, tmp_path, _secrets = client
    doctor = await http.get("/ops/doctor", headers=headers)
    assert doctor.status_code == 200
    doctor_body = doctor.json()
    assert doctor_body["ready"] is True
    checks = doctor_body.get("checks")
    assert isinstance(checks, list)
    assert len(checks) >= 5
    assert all(
        isinstance(item.get("id"), str) and isinstance(item.get("detail"), str) for item in checks
    )
    background_ids = {item["id"] for item in checks if str(item["id"]).startswith("background:")}
    assert "background:index" in background_ids
    assert "background:goals" in background_ids
    assert all(
        item["ok"] is True
        for item in checks
        if str(item["id"]).startswith("background:")
    )
    assert BOT not in str(doctor_body)

    backup = await http.post("/ops/backup", json={"dest": str(tmp_path / "bak")}, headers=headers)
    assert backup.status_code == 200
    assert backup.json()["includes_secret_store"] is False
    assert BOT not in str(backup.json())

    letters = await http.get("/ops/dead-letters", headers=headers)
    assert letters.status_code == 200
    assert letters.json()["items"] == []

    recover = await http.post("/ops/leases/recover", headers=headers)
    assert recover.status_code == 200

    settings = await http.get("/ops/settings", headers=headers)
    assert settings.status_code == 200
    assert settings.json()["otel_export"] is False
    assert "token" not in str(settings.json()).lower() or "bot" not in str(settings.json()).lower()

    saved = await http.put(
        "/ops/settings",
        json={"otel_export": True, "langfuse_export": True},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["otel_export"] is True
    assert saved.json()["langfuse_export"] is True
    doctor = await http.get("/ops/doctor", headers=headers)
    assert doctor.status_code == 200
    sink = tmp_path / "logs" / "otel-export.jsonl"
    assert sink.is_file()
    exported = sink.read_text(encoding="utf-8")
    assert BOT not in exported
    assert "PRIVATE KEY" not in exported
    assert "/ops/doctor" in exported or "doctor" in exported

    updates = await http.get("/ops/updates", headers=headers)
    assert updates.status_code == 200
    assert updates.json()["signed"] is False
    assert updates.json()["compatible"] is True

    notes = await http.get("/ops/notifications", headers=headers)
    assert notes.status_code == 200
    assert "items" in notes.json()


@pytest.mark.asyncio
async def test_ops_token_and_pem_posts_are_not_exposed(
    client: tuple[AsyncClient, dict[str, str], Path, InMemorySecretStore],
) -> None:
    http, headers, _tmp_path, _secrets = client
    for path in ("/ops/token", "/ops/pem"):
        response = await http.post(path, json={"token": BOT, "pem": PEM}, headers=headers)
        assert response.status_code in {403, 404, 405, 422}
        assert BOT not in response.text
    stored = await http.post("/telegram/token", json={"token": BOT}, headers=headers)
    assert stored.status_code == 200
    assert BOT not in stored.text
    assert PEM not in stored.text
