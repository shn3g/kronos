# SPDX-License-Identifier: AGPL-3.0-or-later
"""Doctor, backup/restore, dead letters, stuck leases, and degradation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore, MemoryKeyring

from kronos_engine.adapters.secrets.os_store import OsSecretStore
from kronos_engine.application.doctor import DoctorService
from kronos_engine.application.recorder import Recorder
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.leases import SqliteLeases
from kronos_engine.state.outbox import SqliteOutbox

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
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


def _doctor(tmp_path: Path, secrets: InMemorySecretStore | OsSecretStore) -> DoctorService:
    settings = _settings(tmp_path)
    database = Database(settings.paths.database)
    conn = database.connect()
    recorder = Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn))
    return DoctorService(conn, settings, secrets, recorder=recorder)


def test_backup_excludes_secret_store_and_redacts_tokens(tmp_path: Path) -> None:
    secrets = InMemorySecretStore()
    secrets.put("telegram:bot_token", BOT)
    secrets.put("github:controller:private_key", PEM)
    doctor = _doctor(tmp_path, secrets)
    dest = tmp_path / "backup"
    archive = doctor.backup(dest)
    blob = b""
    for path in Path(archive.path).rglob("*"):
        if path.is_file():
            blob += path.read_bytes()
    assert BOT.encode() not in blob
    assert b"BEGIN RSA PRIVATE KEY" not in blob
    assert b"install-token" not in blob
    assert "secret" not in archive.path.lower() or "secretstore" not in archive.path.lower()
    names = {path.name.lower() for path in Path(archive.path).rglob("*")}
    assert "keyring" not in names
    assert archive.includes_secret_store is False


def test_restore_is_not_ready_when_health_or_version_fail(tmp_path: Path) -> None:
    secrets = InMemorySecretStore()
    doctor = _doctor(tmp_path, secrets)
    archive = doctor.backup(tmp_path / "backup")
    broken = _settings(tmp_path)
    object.__setattr__(broken, "engine_version", "9.0.0")
    object.__setattr__(broken, "min_client_version", "9.0.0")
    restored = DoctorService(
        doctor._conn,
        broken,
        secrets,
        recorder=doctor._recorder,
    ).restore(Path(archive.path), client_version="0.1.0")
    assert restored.ready is False
    assert restored.health == "failed" or restored.compatible is False


def test_dead_letter_inspection_and_stuck_lease_recovery(tmp_path: Path) -> None:
    secrets = InMemorySecretStore()
    doctor = _doctor(tmp_path, secrets)
    doctor.record_dead_letter(
        event_type="external.wrote",
        payload={"url": "https://api.github.com/repos/acme/app/pulls", "token": BOT},
        reason="github throttled",
    )
    letters = doctor.inspect_dead_letters()
    assert len(letters) == 1
    assert letters[0].reason == "github throttled"
    assert BOT not in str(letters[0].payload)
    leases = SqliteLeases(doctor._conn)
    leases.acquire("repo_alpha:area:pkg", "dead-holder", timedelta(seconds=5), now=NOW)
    recovered = doctor.recover_stuck_leases(now=NOW + timedelta(seconds=30))
    assert any(item.resource_key == "repo_alpha:area:pkg" for item in recovered)
    with pytest.raises(Exception):
        leases.assert_fence(
            "repo_alpha:area:pkg",
            recovered[0].fence_token,
            now=NOW + timedelta(seconds=30),
        )


def test_model_and_index_degradation_are_explained(tmp_path: Path) -> None:
    secrets = InMemorySecretStore()
    doctor = _doctor(tmp_path, secrets)
    init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
    report = doctor.check(client_version="0.1.0")
    assert report.ready is True
    doctor.mark_model_degraded("coder", "model outage")
    doctor.mark_index_degraded("repo_alpha", "corrupt cache")
    degraded = doctor.check(client_version="0.1.0")
    assert degraded.model_degraded is True
    assert degraded.index_degraded is True
    assert any("outage" in item.detail.lower() for item in degraded.findings)
    assert any(
        "cache" in item.detail.lower() or "index" in item.detail.lower()
        for item in degraded.findings
    )


def test_doctor_output_never_contains_os_secrets(tmp_path: Path) -> None:
    keyring = MemoryKeyring()
    store = OsSecretStore(tmp_path / "config", backend=keyring)
    store.put("telegram:bot_token", BOT)
    store.put("github:reviewer:private_key", PEM)
    doctor = _doctor(tmp_path, store)
    report = doctor.check(client_version="0.1.0")
    encoded = str(report)
    assert BOT not in encoded
    assert "PRIVATE KEY" not in encoded
    archive = doctor.backup(tmp_path / "backup")
    blob = b"".join(p.read_bytes() for p in Path(archive.path).rglob("*") if p.is_file())
    assert BOT.encode() not in blob
    assert b"BEGIN RSA" not in blob
