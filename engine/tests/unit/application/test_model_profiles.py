# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application model profiles persist config without secrets and assign roles."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from tests.support.secrets import InMemorySecretStore

from kronos_engine.application.model_profiles import (
    ModelProfileService,
    ProviderDraft,
    RoleAssignmentError,
)
from kronos_engine.domain.models import MODEL_ROLES, ModelProfile, ResourceLimits
from kronos_engine.state.database import Database
from kronos_engine.state.model_profiles import SqliteModelRegistry


def _service(tmp_path: Path) -> tuple[ModelProfileService, InMemorySecretStore]:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    store = InMemorySecretStore()
    return ModelProfileService(SqliteModelRegistry(conn), store), store


def _limits() -> ResourceLimits:
    return ResourceLimits(
        max_tokens=1024, max_attempts=3, timeout_seconds=30.0, cost_ceiling=0.0
    )


def test_assignments_require_all_four_roles(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    provider = service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
            api_key=None,
        )
    )
    profile = service.save_profile(
        ModelProfile(
            id="prof_all",
            display_name="Local",
            role="planner",
            provider_id=provider.id,
            model_id="llama3",
            billed=False,
            approved_fallbacks=(),
            limits=_limits(),
        )
    )
    with pytest.raises(RoleAssignmentError, match="missing"):
        service.assign({"planner": profile.id})
    assigned = service.assign({role: profile.id for role in MODEL_ROLES})
    assert assigned.planner == profile.id
    assert assigned.coder == profile.id
    assert assigned.reviewer == profile.id
    assert assigned.embedding == profile.id


def test_scoped_secret_is_short_lived_and_not_on_the_provider(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    provider = service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
            api_key="sk-scoped",
        )
    )
    secret = service.scoped_secret(provider.id, ttl_seconds=15)
    assert secret is not None
    assert secret.value == "sk-scoped"
    assert secret.ttl_seconds == 15
    assert store.get(provider.secret_ref) == "sk-scoped"
    dumped = [asdict(item) for item in service.list_providers()]
    assert all("sk-scoped" not in str(item) for item in dumped)
