# SPDX-License-Identifier: AGPL-3.0-or-later
"""Complete chat turns with the assigned planner profile."""

from __future__ import annotations

from collections.abc import Sequence

from kronos_engine.adapters.models.openai_compatible import OpenAICompatibleProvider
from kronos_engine.application.chat import ChatModelError, ChatTurn
from kronos_engine.ports.model_provider import CompletionRequest, ModelProvider
from kronos_engine.ports.model_registry import ModelRegistry
from kronos_engine.ports.secrets import ScopedSecret, SecretStore

DEFAULT_BASE = "http://127.0.0.1:11434/v1"


class AssignedPlannerCompleter:
    def __init__(
        self,
        registry: ModelRegistry,
        secrets: SecretStore,
        *,
        provider: ModelProvider | None = None,
    ) -> None:
        self._registry = registry
        self._secrets = secrets
        self._provider = provider

    def complete(self, turns: Sequence[ChatTurn], system: str) -> str:
        assignments = self._registry.load_assignments()
        if assignments.planner is None:
            raise ChatModelError("no planner assigned")
        profiles = {item.id: item for item in self._registry.list_profiles()}
        profile = profiles.get(assignments.planner)
        if profile is None:
            raise ChatModelError("planner profile is missing")
        providers = {item.id: item for item in self._registry.list_providers()}
        config = providers.get(profile.provider_id)
        if config is None:
            raise ChatModelError("planner provider is missing")
        secret_value = self._secrets.get(config.secret_ref)
        secret = ScopedSecret(secret_value, ttl_seconds=120) if secret_value else None
        adapter = self._provider or OpenAICompatibleProvider(
            base_url=config.base_url or DEFAULT_BASE,
            billed=config.billed,
        )
        prompt = _flatten(system, turns)
        result = adapter.complete(CompletionRequest(profile=profile, prompt=prompt), secret)
        return result.text


def _flatten(system: str, turns: Sequence[ChatTurn]) -> str:
    parts = [f"SYSTEM\n{system}"]
    for turn in turns:
        parts.append(f"{turn.role.upper()}\n{turn.content}")
    parts.append("ASSISTANT")
    return "\n\n".join(parts)
