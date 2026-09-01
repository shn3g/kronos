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
from kronos_engine.ports.model_registry import ProviderConfig, RoleAssignments
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


def test_assignments_require_all_five_roles(tmp_path: Path) -> None:
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
    assigned = service.assign({role: profile.id for role in MODEL_ROLES}, confirm_shared_roles=True)
    assert assigned.orchestrator == profile.id
    assert assigned.planner == profile.id
    assert assigned.coder == profile.id
    assert assigned.reviewer == profile.id
    assert assigned.embedding == profile.id


def test_register_provider_persists_preset_model_id_on_profiles(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            billed=True,
            api_key=None,
            model_id="gpt-4o-mini",
        )
    )
    profiles = service.list_profiles()
    assert profiles
    assert {item.model_id for item in profiles} == {"gpt-4o-mini"}


def test_register_provider_seeds_five_role_profiles(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
            api_key=None,
        )
    )
    roles = {item.role for item in service.list_profiles()}
    assert roles == set(MODEL_ROLES)


def test_assign_rejects_role_mismatch_without_confirm(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
        )
    )
    profiles = {item.role: item.id for item in service.list_profiles()}
    with pytest.raises(RoleAssignmentError, match="role|confirm"):
        service.assign({role: profiles["coder"] for role in MODEL_ROLES})
    assigned = service.assign(profiles)
    assert assigned.orchestrator == profiles["orchestrator"]
    assert assigned.coder == profiles["coder"]
    assert assigned.planner == profiles["planner"]


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


def test_load_assignments_defaults_missing_orchestrator_to_none(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    loaded = service.assignments()
    assert loaded.orchestrator is None
    assert loaded.as_dict()["orchestrator"] is None
    empty = RoleAssignments(
        orchestrator=None,
        planner=None,
        coder=None,
        reviewer=None,
        embedding=None,
    )
    assert empty.as_dict() == {
        "orchestrator": None,
        "planner": None,
        "coder": None,
        "reviewer": None,
        "embedding": None,
    }


def test_list_profiles_backfills_missing_orchestrator_for_existing_provider(
    tmp_path: Path,
) -> None:
    service, _store = _service(tmp_path)
    provider = ProviderConfig(
        id="prov_legacy",
        kind="openai_compatible",
        display_name="Ollama",
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        secret_ref="provider:prov_legacy:api_key",
    )
    service._registry.save_provider(provider)
    for role in ("planner", "coder", "reviewer", "embedding"):
        service._registry.save_profile(
            ModelProfile(
                id=f"prof_{provider.id}_{role}",
                display_name=f"Ollama ({role})",
                role=role,
                provider_id=provider.id,
                model_id="llama3",
                billed=False,
                approved_fallbacks=(),
                limits=_limits(),
            )
        )
    profiles = service.list_profiles()
    orchestrator = next(item for item in profiles if item.role == "orchestrator")
    assert orchestrator.id == "prof_prov_legacy_orchestrator"
    assert orchestrator.provider_id == "prov_legacy"
    persisted = {item.role for item in service._registry.list_profiles()}
    assert "orchestrator" in persisted


def test_update_profile_changes_model_id_and_limits_only(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    provider = service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
        )
    )
    coder = next(item for item in service.list_profiles() if item.role == "coder")
    updated = service.update_profile(
        coder.id,
        model_id="llama3.1",
        limits=ResourceLimits(
            max_tokens=2048, max_attempts=3, timeout_seconds=60.0, cost_ceiling=2.5
        ),
    )
    assert updated.id == coder.id
    assert updated.role == "coder"
    assert updated.provider_id == provider.id
    assert updated.model_id == "llama3.1"
    assert updated.limits.cost_ceiling == 2.5
    assert updated.limits.max_tokens == 2048
    assert updated.display_name == coder.display_name
