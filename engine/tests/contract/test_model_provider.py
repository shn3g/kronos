# SPDX-License-Identifier: AGPL-3.0-or-later
"""Model provider contract: approved lists, no silent paid fallback, secrets stay out of config."""

from __future__ import annotations

from pathlib import Path

import pytest

from kronos_engine.adapters.models.openai_compatible import OpenAICompatibleProvider
from kronos_engine.domain.models import (
    ModelProfile,
    PaidFallbackRefused,
    ResourceLimits,
    UnapprovedFallbackError,
)
from kronos_engine.ports.model_provider import CompletionRequest
from kronos_engine.ports.secrets import ScopedSecret


class _Transport:
    def __init__(self, *, payload: dict[str, object] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.payload = payload or {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 8},
        }

    def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]:
        self.calls.append({"method": "get", "url": url, "timeout": timeout})
        return 200, {"data": [{"id": "llama3"}]}

    def post(
        self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, object]]:
        self.calls.append(
            {"method": "post", "url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return 200, self.payload


def _profile() -> ModelProfile:
    return ModelProfile(
        id="prof_coder",
        display_name="Local coder",
        role="coder",
        provider_id="prov_ollama",
        model_id="llama3",
        billed=False,
        approved_fallbacks=("llama3.1",),
        limits=ResourceLimits(
            max_tokens=128,
            max_attempts=3,
            timeout_seconds=15.0,
            cost_ceiling=0.0,
        ),
    )


def test_completion_uses_scoped_secret_not_stored_on_the_profile() -> None:
    transport = _Transport()
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        transport=transport,
    )
    secret = ScopedSecret(value="sk-live-secret", ttl_seconds=30)
    result = provider.complete(
        CompletionRequest(profile=_profile(), prompt="hello"),
        secret=secret,
    )
    assert result.text == "ok"
    assert result.usage.tokens == 8
    posted = next(call for call in transport.calls if call["method"] == "post")
    headers = posted["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer sk-live-secret"
    assert "sk-live-secret" not in repr(secret)
    assert "sk-live-secret" not in str(secret)


def test_unapproved_fallback_fails_before_http() -> None:
    transport = _Transport()
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        transport=transport,
    )
    with pytest.raises(UnapprovedFallbackError):
        provider.complete(
            CompletionRequest(
                profile=_profile(),
                prompt="hello",
                fallback_model_id="gpt-4",
                fallback_billed=True,
            ),
            secret=None,
        )
    assert transport.calls == []


def test_paid_fallback_fails_deterministically() -> None:
    transport = _Transport()
    provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        billed=True,
        transport=transport,
    )
    profile = _profile()
    profile = ModelProfile(
        id=profile.id,
        display_name=profile.display_name,
        role=profile.role,
        provider_id=profile.provider_id,
        model_id=profile.model_id,
        billed=False,
        approved_fallbacks=("gpt-4",),
        limits=profile.limits,
    )
    with pytest.raises(PaidFallbackRefused):
        provider.complete(
            CompletionRequest(
                profile=profile,
                prompt="hello",
                fallback_model_id="gpt-4",
                fallback_billed=True,
            ),
            secret=ScopedSecret(value="sk-paid", ttl_seconds=30),
        )
    assert transport.calls == []


def test_provider_config_file_never_contains_secret_values(tmp_path: Path) -> None:
    from tests.support.secrets import InMemorySecretStore

    from kronos_engine.application.model_profiles import ModelProfileService, ProviderDraft
    from kronos_engine.state.database import Database
    from kronos_engine.state.model_profiles import SqliteModelRegistry

    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    store = InMemorySecretStore()
    service = ModelProfileService(SqliteModelRegistry(conn), store)
    provider = service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Ollama",
            base_url="http://127.0.0.1:11434/v1",
            billed=False,
            api_key="sk-must-not-persist",
        )
    )
    listed = service.list_providers()
    assert listed[0].id == provider.id
    assert listed[0].api_key is None
    raw = (tmp_path / "kronos.sqlite3").read_bytes()
    assert b"sk-must-not-persist" not in raw
    assert store.get(provider.secret_ref) == "sk-must-not-persist"
    conn.close()
