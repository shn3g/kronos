# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resolve the embedding role: assigned profile, then local ONNX, then sparse-only."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.adapters.embeddings.local import (
    CODE_MODEL_ID,
    DOCUMENT_MODEL_ID,
    LocalEmbeddingAdapter,
)
from kronos_engine.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddingAdapter
from kronos_engine.adapters.models.openai_compatible import HttpTransport
from kronos_engine.ports.embedding import EmbeddingPort
from kronos_engine.ports.model_registry import ModelRegistry
from kronos_engine.ports.secrets import ScopedSecret, SecretStore

_SECRET_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class EmbeddingBackend:
    kind: str
    model_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class ResolvedEmbedder:
    adapter: EmbeddingPort
    backend: EmbeddingBackend


class UnavailableEmbeddingAdapter:
    def available(self, kind: str) -> bool:
        _ = kind
        return False

    def embed(self, texts: Sequence[str], *, kind: str) -> Sequence[Sequence[float]] | None:
        _ = texts, kind
        return None


def resolve_embedder(
    registry: ModelRegistry,
    secrets: SecretStore,
    models_dir: Path,
    *,
    transport: HttpTransport | None = None,
) -> ResolvedEmbedder:
    assigned = _from_assignment(registry, secrets, transport=transport)
    if assigned is not None:
        return assigned
    local = LocalEmbeddingAdapter(models_dir)
    if local.available("document") or local.available("code"):
        model_id = DOCUMENT_MODEL_ID if local.available("document") else CODE_MODEL_ID
        return ResolvedEmbedder(
            adapter=local,
            backend=EmbeddingBackend(kind="onnx", model_id=model_id, display_name="Local ONNX"),
        )
    return ResolvedEmbedder(
        adapter=UnavailableEmbeddingAdapter(),
        backend=EmbeddingBackend(kind="none", model_id="", display_name="Sparse only"),
    )


def _from_assignment(
    registry: ModelRegistry,
    secrets: SecretStore,
    *,
    transport: HttpTransport | None,
) -> ResolvedEmbedder | None:
    profile_id = registry.load_assignments().embedding
    if not profile_id:
        return None
    profiles = {item.id: item for item in registry.list_profiles()}
    profile = profiles.get(profile_id)
    if profile is None:
        return None
    providers = {item.id: item for item in registry.list_providers()}
    provider = providers.get(profile.provider_id)
    if provider is None or not provider.base_url:
        return None
    raw = secrets.get(provider.secret_ref)
    secret = ScopedSecret(value=raw, ttl_seconds=_SECRET_TTL_SECONDS) if raw else None
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url=provider.base_url,
        model_id=profile.model_id,
        billed=provider.billed or profile.billed,
        secret=secret,
        transport=transport,
    )
    if not adapter.available("document") and not adapter.available("code"):
        return None
    return ResolvedEmbedder(
        adapter=adapter,
        backend=EmbeddingBackend(
            kind="openai_compatible",
            model_id=profile.model_id,
            display_name=profile.display_name,
        ),
    )
