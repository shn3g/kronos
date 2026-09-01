# SPDX-License-Identifier: AGPL-3.0-or-later
"""Complete chat turns with the assigned planner profile."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from threading import Event

from kronos_engine.adapters.models.openai_compatible import (
    CompletionCancelled,
    OpenAICompatibleProvider,
)
from kronos_engine.application.chat import ChatModelError, ChatTurn, ChatTurnCancelled
from kronos_engine.ports.model_provider import CompletionRequest, ModelProvider
from kronos_engine.ports.model_registry import ModelRegistry
from kronos_engine.ports.secrets import ScopedSecret, SecretStore

DEFAULT_BASE = "http://127.0.0.1:11434/v1"


def chat_completion_messages(system: str, turns: Sequence[ChatTurn]) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": system}]
    for turn in turns:
        if turn.role == "assistant":
            messages.append({"role": "assistant", "content": turn.content})
            continue
        if turn.role == "tool":
            messages.append({"role": "user", "content": f"[tool]\n{turn.content}"})
            continue
        messages.append({"role": "user", "content": turn.content})
    return messages


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

    def complete(
        self,
        turns: Sequence[ChatTurn],
        system: str,
        *,
        cancel: Event | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        adapter, request, secret = self._bound_request(turns, system)
        stream = getattr(adapter, "complete_stream", None)
        if callable(stream):
            return _consume_stream(stream, request, secret, cancel, on_delta)
        result = adapter.complete(request, secret)
        if on_delta is not None and result.text:
            on_delta(result.text)
        return result.text

    def _bound_request(
        self, turns: Sequence[ChatTurn], system: str
    ) -> tuple[ModelProvider, CompletionRequest, ScopedSecret | None]:
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
        messages = tuple(chat_completion_messages(system, turns))
        return (
            adapter,
            CompletionRequest(profile=profile, prompt=prompt, messages=messages),
            secret,
        )


def _consume_stream(
    stream: Callable[..., Iterator[str]],
    request: CompletionRequest,
    secret: ScopedSecret | None,
    cancel: Event | None,
    on_delta: Callable[[str], None] | None,
) -> str:
    parts: list[str] = []
    try:
        for chunk in stream(request, secret, cancel=cancel or Event()):
            parts.append(chunk)
            if on_delta is not None:
                on_delta(chunk)
        return "".join(parts)
    except CompletionCancelled as error:
        raise ChatTurnCancelled(error.partial or "".join(parts)) from error


def _flatten(system: str, turns: Sequence[ChatTurn]) -> str:
    parts = [f"SYSTEM\n{system}"]
    for turn in turns:
        parts.append(f"{turn.role.upper()}\n{turn.content}")
    parts.append("ASSISTANT")
    return "\n\n".join(parts)
