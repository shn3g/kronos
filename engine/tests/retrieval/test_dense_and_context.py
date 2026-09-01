# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest
from tests.retrieval.support import (
    indexing_policy,
    kronos_paths,
    write_local_embedding_fixtures,
    write_tiny_token_embedding_onnx,
    write_tiny_tokenizer,
)
from tests.support.git_fixtures import init_git_repo

from kronos_engine.adapters.embeddings.local import (
    DOCUMENT_FILENAME,
    DOCUMENT_MODEL_ID,
    DOCUMENT_MODEL_LICENSE,
    EmbeddingModelConfig,
    LocalEmbeddingAdapter,
)
from kronos_engine.indexing.service import IndexingService
from kronos_engine.ports.embedding import EmbeddingPort


class _UnavailableEmbedding:
    def available(self, kind: str) -> bool:
        _ = kind
        return False

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]] | None:
        _ = texts, kind
        return None


class _RecordingEmbedding:
    def __init__(self) -> None:
        self.kinds: list[str] = []
        self.batches: list[tuple[str, tuple[str, ...]]] = []

    def available(self, kind: str) -> bool:
        _ = kind
        return True

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        payload = tuple(texts)
        self.kinds.append(kind)
        self.batches.append((kind, payload))
        dim = 8
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * dim
            for index, char in enumerate(text.encode("utf-8")):
                vector[index % dim] += float(char)
            vectors.append(vector)
        return vectors


class _SpyEmbedding:
    def __init__(self, inner: LocalEmbeddingAdapter) -> None:
        self._inner = inner
        self.batches: list[tuple[str, tuple[str, ...]]] = []

    def available(self, kind: str) -> bool:
        return self._inner.available(kind)

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]] | None:
        self.batches.append((kind, tuple(texts)))
        result = self._inner.embed(texts, kind=kind)
        return None if result is None else [list(row) for row in result]


def test_dense_degrades_when_model_file_is_absent(tmp_path: Path) -> None:
    adapter = LocalEmbeddingAdapter(models_dir=tmp_path / "models")
    assert adapter.available("code") is False
    assert adapter.available("document") is False
    assert adapter.embed(["hello"], kind="code") is None
    assert adapter.embed(["hello"], kind="document") is None
    engine_src = Path(__file__).resolve().parents[2] / "src" / "kronos_engine"
    module_file = engine_src / "adapters" / "embeddings" / "local.py"
    text = module_file.read_text(encoding="utf-8")
    blocked = (
        "urllib",
        "httpx",
        "huggingface",
        "sentence_transformers",
        "requests",
        "wget",
    )
    for name in blocked:
        assert name not in text
    assert "all-MiniLM-L6-v2" in text or "all_minilm" in text.lower()
    assert "_hash_features" not in text
    assert "tokenizer.json" in text


def test_minilm_document_path_never_embeds_source_code(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "mix",
        files={
            "src/code.py": "def enrol():\n    return 1\n",
            "docs/guide.md": "English documentation about enrolment.\n",
        },
    )
    embeddings = _RecordingEmbedding()
    service = IndexingService(paths, embeddings=embeddings)
    service.rebuild("repo_mix", root, indexing_policy())
    assert "code" in embeddings.kinds
    assert "document" in embeddings.kinds
    document_texts = [
        text for kind, batch in embeddings.batches if kind == "document" for text in batch
    ]
    code_texts = [text for kind, batch in embeddings.batches if kind == "code" for text in batch]
    assert any("def enrol" in text for text in code_texts)
    assert any("documentation" in text.lower() for text in document_texts)
    assert not any("def enrol" in text for text in document_texts)
    status = service.status("repo_mix")
    assert status.dense_available is True
    _ = EmbeddingPort


def test_onnx_weights_without_tokenizer_leave_dense_unavailable_sparse_works(
    tmp_path: Path,
) -> None:
    pytest.importorskip("onnxruntime")
    models = tmp_path / "models"
    write_tiny_token_embedding_onnx(models / "code.onnx")
    adapter = LocalEmbeddingAdapter(models)
    assert adapter.available("code") is False
    assert adapter.available("document") is False
    assert adapter.embed(["def visible():\n    return 'ok'\n"], kind="code") is None

    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "no-tokenizer",
        files={"src/mod.py": "def visible():\n    return 'ok'\n"},
    )
    service = IndexingService(paths, embeddings=adapter)
    status = service.rebuild("repo_no_tok", root, indexing_policy())
    assert status.dense_available is False
    hits = service.search("repo_no_tok", "visible")
    assert any(item.path.endswith("mod.py") for item in hits.items)
    assert all("dense" not in item.rank_sources for item in hits.items)


def test_local_onnx_file_produces_code_vectors_and_never_uses_minilm(
    tmp_path: Path,
) -> None:
    pytest.importorskip("onnxruntime")
    pytest.importorskip("tokenizers")
    models = write_local_embedding_fixtures(tmp_path / "models")
    adapter = LocalEmbeddingAdapter(models)
    assert adapter.available("code") is True
    assert adapter.available("document") is True
    vectors = adapter.embed(["def enrol():\n    return 1\n"], kind="code")
    assert vectors is not None
    assert len(vectors) == 1
    assert len(vectors[0]) >= 1
    assert all(isinstance(value, float) for value in vectors[0])
    minilm_as_code = LocalEmbeddingAdapter(
        models,
        code=EmbeddingModelConfig(
            model_id=DOCUMENT_MODEL_ID,
            license=DOCUMENT_MODEL_LICENSE,
            filename=DOCUMENT_FILENAME,
            sha256="",
        ),
    )
    assert minilm_as_code.available("code") is False
    assert minilm_as_code.embed(["def enrol():\n    pass\n"], kind="code") is None

    spy = _SpyEmbedding(adapter)
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "onnx-mix",
        files={
            "src/code.py": "def enrol():\n    return 1\n",
            "docs/guide.md": "English documentation about enrolment.\n",
        },
    )
    service = IndexingService(paths, embeddings=spy)
    status = service.rebuild("repo_onnx", root, indexing_policy())
    assert status.dense_available is True
    code_texts = [text for kind, batch in spy.batches if kind == "code" for text in batch]
    document_texts = [text for kind, batch in spy.batches if kind == "document" for text in batch]
    assert any("def enrol" in text for text in code_texts)
    assert any("documentation" in text.lower() for text in document_texts)
    assert not any("def enrol" in text for text in document_texts)


def test_unloadable_onnx_degrades_without_raising(tmp_path: Path) -> None:
    pytest.importorskip("onnxruntime")
    models = tmp_path / "models"
    models.mkdir()
    (models / "code.onnx").write_bytes(b"not a valid onnx file")
    write_tiny_tokenizer(models / "tokenizer.json")
    adapter = LocalEmbeddingAdapter(models)
    assert adapter.available("code") is False
    assert adapter.embed(["def enrol():\n    pass\n"], kind="code") is None

    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "junk-onnx",
        files={"src/mod.py": "def visible():\n    return 'ok'\n"},
    )
    service = IndexingService(paths, embeddings=adapter)
    status = service.rebuild("repo_junk", root, indexing_policy())
    assert status.dense_available is False
    hits = service.search("repo_junk", "visible")
    assert any(item.path.endswith("mod.py") for item in hits.items)
    assert all("dense" not in item.rank_sources for item in hits.items)


def test_sparse_and_graph_still_serve_without_dense(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "plain",
        files={"src/mod.py": "def visible():\n    return 'ok'\n"},
    )
    service = IndexingService(paths, embeddings=_UnavailableEmbedding())
    status = service.rebuild("repo_plain", root, indexing_policy())
    assert status.dense_available is False
    hits = service.search("repo_plain", "visible")
    assert any(item.path.endswith("mod.py") for item in hits.items)
    assert all("dense" not in item.rank_sources for item in hits.items)


def test_context_items_include_provenance_and_repo_map_respects_token_budget(
    tmp_path: Path,
) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "ctx",
        files={
            "src/a.py": "def alpha():\n    return 1\n",
            "src/b.py": "def beta():\n    return 2\n",
        },
    )
    service = IndexingService(paths)
    service.rebuild("repo_ctx", root, indexing_policy())
    pack = service.search("repo_ctx", "alpha", budget_tokens=40)
    assert pack.items
    item = pack.items[0]
    assert item.path
    assert item.start_line >= 1
    assert item.end_line >= item.start_line
    assert item.commit
    assert item.rank_sources
    assert item.trust
    mapped = service.repo_map("repo_ctx", budget_tokens=12)
    assert mapped
    assert len(mapped.split()) <= 24
