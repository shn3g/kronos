# SPDX-License-Identifier: AGPL-3.0-or-later
"""Embedding role resolver: assigned profile, then local ONNX, then sparse-only."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.retrieval.support import write_local_embedding_fixtures
from tests.support.secrets import InMemorySecretStore

from kronos_engine.application.embeddings import resolve_embedder
from kronos_engine.application.model_profiles import ModelProfileService, ProviderDraft
from kronos_engine.domain.models import MODEL_ROLES, ResourceLimits
from kronos_engine.state.database import Database
from kronos_engine.state.model_profiles import SqliteModelRegistry


def _service(tmp_path: Path) -> tuple[ModelProfileService, InMemorySecretStore, Path]:
    database = Database(tmp_path / "kronos.sqlite3")
    conn = database.connect()
    store = InMemorySecretStore()
    return ModelProfileService(SqliteModelRegistry(conn), store), store, tmp_path / "models"


def test_resolver_uses_assigned_embedding_profile_before_onnx(tmp_path: Path) -> None:
    service, secrets, models_dir = _service(tmp_path)
    write_local_embedding_fixtures(models_dir)
    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Remote embed",
            base_url="https://api.openai.com/v1",
            billed=True,
            api_key="sk-embed",
        )
    )
    profiles = {item.role: item for item in service.list_profiles()}
    service.update_profile(
        profiles["embedding"].id,
        model_id=profiles["embedding"].model_id,
        limits=ResourceLimits(
            max_tokens=4096, max_attempts=3, timeout_seconds=120.0, cost_ceiling=1.0
        ),
    )
    service.assign({role: profiles[role].id for role in MODEL_ROLES})
    resolved = resolve_embedder(service._registry, secrets, models_dir)
    assert resolved.backend.kind == "openai_compatible"
    assert resolved.backend.model_id == "default"
    assert resolved.backend.display_name == profiles["embedding"].display_name
    assert resolved.adapter.available("document") is True


def test_resolver_falls_back_to_onnx_when_weights_and_tokenizer_exist(tmp_path: Path) -> None:
    pytest.importorskip("onnxruntime")
    pytest.importorskip("tokenizers")
    service, secrets, models_dir = _service(tmp_path)
    write_local_embedding_fixtures(models_dir)
    resolved = resolve_embedder(service._registry, secrets, models_dir)
    assert resolved.backend.kind == "onnx"
    assert resolved.backend.model_id
    assert resolved.adapter.available("document") is True
    vectors = resolved.adapter.embed(["hello world"], kind="document")
    assert vectors is not None
    assert len(vectors[0]) >= 1


def test_resolver_sparse_only_when_no_profile_and_no_local_model(tmp_path: Path) -> None:
    service, secrets, models_dir = _service(tmp_path)
    resolved = resolve_embedder(service._registry, secrets, models_dir)
    assert resolved.backend.kind == "none"
    assert resolved.adapter.available("document") is False
    assert resolved.adapter.available("code") is False
    assert resolved.adapter.embed(["hello"], kind="document") is None


def test_malformed_assigned_embedding_url_does_not_raise(tmp_path: Path) -> None:
    service, secrets, models_dir = _service(tmp_path)
    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Broken URL",
            base_url="http://[",
            billed=False,
            api_key="sk-embed",
        )
    )
    profiles = {item.role: item for item in service.list_profiles()}
    service.assign({role: profiles[role].id for role in MODEL_ROLES})
    try:
        resolved = resolve_embedder(service._registry, secrets, models_dir)
        available = resolved.adapter.available("document")
        vectors = resolved.adapter.embed(["hello"], kind="document")
    except Exception as exc:
        raise AssertionError(
            f"resolve/available/embed raised {type(exc).__name__}: {exc}"
        ) from exc
    assert resolved.backend.kind == "none"
    assert available is False
    assert vectors is None


def test_billed_assigned_embedder_with_zero_ceiling_does_not_post(tmp_path: Path) -> None:
    service, secrets, models_dir = _service(tmp_path)

    class _Transport:
        def __init__(self) -> None:
            self.posts = 0

        def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]:
            _ = url, timeout
            return 200, {}

        def post(
            self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float
        ) -> tuple[int, dict[str, object]]:
            _ = url, json, headers, timeout
            self.posts += 1
            return 200, {"data": [{"embedding": [0.1, 0.2], "index": 0}]}

    transport = _Transport()
    service.register_provider(
        ProviderDraft(
            kind="openai_compatible",
            display_name="Paid embed",
            base_url="https://api.openai.com/v1",
            billed=True,
            api_key="sk-embed",
        )
    )
    profiles = {item.role: item for item in service.list_profiles()}
    service.update_profile(
        profiles["embedding"].id,
        model_id=profiles["embedding"].model_id,
        limits=ResourceLimits(
            max_tokens=1024, max_attempts=1, timeout_seconds=15.0, cost_ceiling=0.0
        ),
    )
    service.assign({role: profiles[role].id for role in MODEL_ROLES})
    resolved = resolve_embedder(service._registry, secrets, models_dir, transport=transport)
    assert resolved.adapter.available("document") is False
    assert resolved.adapter.available("code") is False
    assert resolved.adapter.embed(["hello"], kind="document") is None
    assert transport.posts == 0


def test_composition_and_app_resolve_the_embedding_role() -> None:
    engine_src = Path(__file__).resolve().parents[3] / "src" / "kronos_engine"
    composition = (engine_src / "application" / "composition.py").read_text(encoding="utf-8")
    app = (engine_src / "api" / "app.py").read_text(encoding="utf-8")
    assert "LocalEmbeddingAdapter(" not in composition
    assert "LocalEmbeddingAdapter(" not in app
    assert "resolve_embedder" in composition
    assert "resolve_embedder" in app
    assert "backfill_memory_vectors" in app
    assert "embedding_startup.append(_warm_embeddings)" in app
    assert app.count("_warm_embeddings()") == 1
