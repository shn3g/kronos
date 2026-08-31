# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests.retrieval.support import indexing_policy, kronos_paths
from tests.support.git_fixtures import init_git_repo

from kronos_engine.adapters.embeddings.local import LocalEmbeddingAdapter
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

    def available(self, kind: str) -> bool:
        _ = kind
        return True

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        self.kinds.append(kind)
        dim = 8
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * dim
            for index, char in enumerate(text.encode("utf-8")):
                vector[index % dim] += float(char)
            vectors.append(vector)
        return vectors


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
    assert "document" in embeddings.kinds
    # Source code uses the code kind, never the English MiniLM document kind.
    dense_file = (
        Path(__file__).resolve().parents[2] / "src" / "kronos_engine" / "indexing" / "dense.py"
    )
    text = dense_file.read_text(encoding="utf-8")
    assert "document" in text
    assert "code" in text
    status = service.status("repo_mix")
    assert status.dense_available is True
    _ = EmbeddingPort


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
