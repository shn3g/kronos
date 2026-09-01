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
from kronos_engine.ports.secrets import SecretStore
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


def _doctor(tmp_path: Path, secrets: SecretStore) -> DoctorService:
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


def test_updates_report_missing_checksums_sbom_and_provenance(tmp_path: Path) -> None:
    secrets = InMemorySecretStore()
    doctor = _doctor(tmp_path, secrets)
    payload = doctor.updates(client_version="0.1.0")
    assert payload["checksums_present"] is False
    assert payload["sbom_present"] is False
    assert payload["provenance_present"] is False
    assert payload["signed"] is False
    doctor._settings.paths.config.mkdir(parents=True, exist_ok=True)
    sums = doctor._settings.paths.config / "SHA256SUMS"
    sums.write_text("deadbeef  Kronos.exe\n", encoding="utf-8")
    present = doctor.updates(client_version="0.1.0")
    assert present["checksums_present"] is True
    assert present["sbom_present"] is False
    assert present["signed"] is False


def test_restore_is_not_ready_when_archive_db_missing_or_corrupt(tmp_path: Path) -> None:
    secrets = InMemorySecretStore()
    doctor = _doctor(tmp_path, secrets)
    live = doctor.check(client_version="0.1.0")
    assert live.ready is True

    missing = tmp_path / "missing-archive"
    missing.mkdir()
    absent = doctor.restore(missing, client_version="0.1.0")
    assert absent.ready is False
    assert absent.health == "failed"

    garbage = tmp_path / "garbage-archive"
    garbage.mkdir()
    (garbage / "kronos.sqlite3").write_bytes(b"not-a-sqlite-database")
    corrupt = doctor.restore(garbage, client_version="0.1.0")
    assert corrupt.ready is False
    assert corrupt.health == "failed"
    restored_path = doctor._settings.paths.database
    assert restored_path.read_bytes().startswith(b"not-a-sqlite-database")


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


def test_dashboard_surfaces_daily_dispatches_not_hardcoded_attempts(
    tmp_path: Path,
) -> None:
    secrets = InMemorySecretStore()
    doctor = _doctor(tmp_path, secrets)
    from kronos_engine.domain.budgets import BudgetMeter
    from kronos_engine.domain.entities import RepositoryId

    doctor._goals.save_budget_meter(
        RepositoryId("repo_alpha"),
        BudgetMeter(
            attempts=0,
            daily_dispatches=7,
            consecutive_failures=2,
            breaker_open=True,
            day="2026-08-31",
        ),
    )
    doctor._recorder.emit(
        "git.wrote",
        {
            "path": "pkg/alpha.py",
            "summary": "+2",
            "repository_id": "repo_alpha",
            "patch": "--- a/pkg/alpha.py\n+++ b/pkg/alpha.py\n@@ -1 +1 @@\n-old\n+new\n",
        },
    )
    snap = doctor.dashboard(client_version="0.1.0")
    assert snap.budgets
    meter = snap.budgets[0]
    assert meter["daily_dispatches"] == 7
    assert meter["breaker_open"] is True
    assert meter["attempts"] == 7
    assert snap.diffs
    assert snap.diffs[0]["repository_id"] == "repo_alpha"
    assert "-old" in str(snap.diffs[0]["patch"])

    doctor._recorder.emit(
        "git.reverted",
        {"path": "pkg/alpha.py", "repository_id": "repo_alpha", "summary": "Reverted pkg/alpha.py"},
    )
    after_revert = doctor.dashboard(client_version="0.1.0")
    assert not any(item["path"] == "pkg/alpha.py" for item in after_revert.diffs)


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


class _BrokenSecretStore:
    def put(self, name: str, value: str) -> None:
        raise RuntimeError(name)

    def get(self, name: str) -> str | None:
        raise RuntimeError("plaintext keyring leak")

    def delete(self, name: str) -> None:
        raise RuntimeError(name)


def test_doctor_marks_secrets_unhealthy_when_store_cannot_be_read(tmp_path: Path) -> None:
    doctor = _doctor(tmp_path, _BrokenSecretStore())
    report = doctor.check(client_version="0.1.0")
    secrets = next(item for item in report.checks if item.id == "secrets")
    assert secrets.ok is False
    assert "not available" in secrets.detail.lower()
    assert "plaintext" not in secrets.detail.lower()
    assert "leak" not in secrets.detail.lower()


def test_doctor_exposes_named_health_checks(tmp_path: Path) -> None:
    doctor = _doctor(tmp_path, InMemorySecretStore())
    report = doctor.check(client_version="0.1.0")
    ids = [item.id for item in report.checks]
    assert ids == ["engine", "model", "workspace", "index", "secrets"]
    engine = next(item for item in report.checks if item.id == "engine")
    assert engine.ok is True
    model = next(item for item in report.checks if item.id == "model")
    assert model.ok is False
    secrets = next(item for item in report.checks if item.id == "secrets")
    assert secrets.ok is True
    assert "secret store" in secrets.detail.lower()
