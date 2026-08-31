# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guided App onboarding stores keys in SecretStore, never SQLite or logs."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.support.github_fixture import TEST_CONTROLLER_PEM, TEST_REVIEWER_PEM, controller_stack
from tests.support.secrets import InMemorySecretStore

from kronos_engine.application.github_setup import GitHubSetupService
from kronos_engine.ports.forge import ForgeAuthError
from kronos_engine.state.database import Database
from kronos_engine.state.github_apps import SqliteGithubAppStore


def test_registering_apps_keeps_private_keys_out_of_sqlite(tmp_path: Path) -> None:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    store = InMemorySecretStore()
    _forge, fixture, _auth = controller_stack(secrets=store)
    service = GitHubSetupService(
        apps=SqliteGithubAppStore(conn),
        secrets=store,
        transport=fixture,
    )
    controller = service.register_app(
        role="controller",
        app_id=1001,
        slug="kronos-controller",
        private_key=TEST_CONTROLLER_PEM,
    )
    reviewer = service.register_app(
        role="reviewer",
        app_id=1002,
        slug="kronos-reviewer",
        private_key=TEST_REVIEWER_PEM,
    )
    service.record_installation("controller", 2001)
    service.record_installation("reviewer", 2002)
    verified = service.verify_installation("controller")
    assert controller.role == "controller"
    assert reviewer.role == "reviewer"
    assert verified.verified is True
    db_bytes = (tmp_path / "kronos.sqlite3").read_bytes()
    assert b"BEGIN RSA PRIVATE KEY" not in db_bytes
    assert TEST_CONTROLLER_PEM.encode() not in db_bytes
    assert TEST_REVIEWER_PEM.encode() not in db_bytes
    assert store.get("github:controller:private_key") == TEST_CONTROLLER_PEM
    token = service.mint_installation_token("controller")
    assert "ghs_" in token.require_fresh()
    assert token.require_fresh() not in str(store.values)
    with pytest.raises(ForgeAuthError):
        GitHubSetupService(
            apps=SqliteGithubAppStore(conn),
            secrets=InMemorySecretStore(),
            transport=fixture,
        ).mint_installation_token("reviewer")
    conn.close()
