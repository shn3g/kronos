# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assign planner/coder/reviewer/embedding profiles. Secrets stay in the store."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from kronos_engine.domain.models import MODEL_ROLES, ModelProfile, ResourceLimits
from kronos_engine.ports.model_registry import ModelRegistry, ProviderConfig, RoleAssignments
from kronos_engine.ports.secrets import ScopedSecret, SecretStore

DEFAULT_LIMITS = ResourceLimits(
    max_tokens=4096,
    max_attempts=3,
    timeout_seconds=120.0,
    cost_ceiling=0.0,
)


class RoleAssignmentError(ValueError):
    """Raised when role assignments are incomplete or unknown."""


@dataclass(frozen=True, slots=True)
class ProviderDraft:
    kind: str
    display_name: str
    base_url: str | None
    billed: bool
    api_key: str | None = None


class ModelProfileService:
    def __init__(self, registry: ModelRegistry, secrets: SecretStore) -> None:
        self._registry = registry
        self._secrets = secrets

    def register_provider(self, draft: ProviderDraft) -> ProviderConfig:
        provider_id = f"prov_{uuid4().hex[:10]}"
        secret_ref = f"provider:{provider_id}:api_key"
        provider = ProviderConfig(
            id=provider_id,
            kind=draft.kind,
            display_name=draft.display_name,
            base_url=draft.base_url,
            billed=draft.billed,
            secret_ref=secret_ref,
            api_key=None,
        )
        self._registry.save_provider(provider)
        if draft.api_key:
            self._secrets.put(secret_ref, draft.api_key)
        for role in MODEL_ROLES:
            self._registry.save_profile(
                ModelProfile(
                    id=f"prof_{provider_id}_{role}",
                    display_name=f"{draft.display_name} ({role})",
                    role=role,
                    provider_id=provider_id,
                    model_id="default",
                    billed=draft.billed,
                    approved_fallbacks=(),
                    limits=DEFAULT_LIMITS,
                )
            )
        return provider

    def save_profile(self, profile: ModelProfile) -> ModelProfile:
        self._registry.save_profile(profile)
        return profile

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        return tuple(self._registry.list_providers())

    def list_profiles(self) -> tuple[ModelProfile, ...]:
        return tuple(self._registry.list_profiles())

    def assign(
        self, assignments: Mapping[str, str], *, confirm_shared_roles: bool = False
    ) -> RoleAssignments:
        missing = [role for role in MODEL_ROLES if role not in assignments or not assignments[role]]
        if missing:
            raise RoleAssignmentError(f"missing role assignments: {missing}")
        known = {profile.id: profile for profile in self._registry.list_profiles()}
        unknown = [role for role, profile_id in assignments.items() if profile_id not in known]
        if unknown:
            raise RoleAssignmentError(f"unknown profiles for roles: {unknown}")
        mismatched = [
            role
            for role, profile_id in assignments.items()
            if role in MODEL_ROLES and known[profile_id].role != role
        ]
        if mismatched and not confirm_shared_roles:
            raise RoleAssignmentError(
                "profile role does not match slot; confirm shared local model"
            )
        result = RoleAssignments(
            planner=assignments["planner"],
            coder=assignments["coder"],
            reviewer=assignments["reviewer"],
            embedding=assignments["embedding"],
        )
        self._registry.save_assignments(result)
        return result

    def assignments(self) -> RoleAssignments:
        return self._registry.load_assignments()

    def scoped_secret(self, provider_id: str, ttl_seconds: int) -> ScopedSecret | None:
        providers = [item for item in self._registry.list_providers() if item.id == provider_id]
        if not providers:
            return None
        value = self._secrets.get(providers[0].secret_ref)
        if value is None:
            return None
        return ScopedSecret(value=value, ttl_seconds=ttl_seconds)
