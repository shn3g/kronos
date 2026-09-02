# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest
from tests.retrieval.support import commit_tree, indexing_policy, kronos_paths, write_and_commit
from tests.support.git_fixtures import init_git_repo

from kronos_engine.indexing.scanner import list_dirty_paths
from kronos_engine.indexing.service import IndexingService
from kronos_engine.indexing.sparse import SqliteIndexStore
from kronos_engine.ports.embedding import EmbeddingIdentity, EmbeddingPort


class _CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0
        self.texts: list[str] = []

    def available(self, kind: str) -> bool:
        _ = kind
        return True

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        _ = kind
        self.calls += 1
        self.texts.extend(texts)
        dim = 4
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * dim
            for index, char in enumerate(text.encode("utf-8")):
                vector[index % dim] += float(char)
            vectors.append(vector)
        return vectors


def test_uncommitted_edit_is_searchable_without_rebuild(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "dirty-search",
        files={"src/mod.py": "OLD_BLOB_TOKEN = 1\n"},
    )
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    policy = indexing_policy()
    service.rebuild("repo_dirty", root, policy)
    assert service.search("repo_dirty", "OLD_BLOB_TOKEN", mode="sparse").items
    (root / "src/mod.py").write_text("NEW_WORKING_TREE_TOKEN = 2\n", encoding="utf-8")
    service.incremental("repo_dirty", root, policy)
    assert service.search("repo_dirty", "OLD_BLOB_TOKEN", mode="sparse").items == ()
    hits = service.search("repo_dirty", "NEW_WORKING_TREE_TOKEN", mode="sparse")
    assert any(item.path.endswith("mod.py") for item in hits.items)


def test_commit_of_previously_dirty_file_replaces_working_tree_chunks(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "dirty-commit",
        files={"src/mod.py": "BASE_TOKEN = 1\n"},
    )
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    policy = indexing_policy()
    service.rebuild("repo_commit", root, policy)
    (root / "src/mod.py").write_text("DIRTY_THEN_COMMITTED = 2\n", encoding="utf-8")
    service.incremental("repo_commit", root, policy)
    store = SqliteIndexStore(paths.cache / "indexes" / "repo_commit" / "index.sqlite3")
    try:
        dirty = store.dirty_paths()
    finally:
        store.close()
    assert "src/mod.py" in dirty
    write_and_commit(root, {"src/mod.py": "DIRTY_THEN_COMMITTED = 2\n"}, "commit dirty")
    service.incremental("repo_commit", root, policy)
    store = SqliteIndexStore(paths.cache / "indexes" / "repo_commit" / "index.sqlite3")
    try:
        assert store.dirty_paths() == ()
    finally:
        store.close()
    hits = service.search("repo_commit", "DIRTY_THEN_COMMITTED")
    assert any(item.path.endswith("mod.py") for item in hits.items)


def test_unchanged_chunks_are_not_reembedded(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "hash-cache",
        files={"src/mod.py": "STABLE_TOKEN = 1\n"},
    )
    embedder = _CountingEmbedder()
    service = IndexingService(paths, embeddings=embedder)
    policy = indexing_policy()
    service.rebuild("repo_hash", root, policy)
    assert embedder.calls >= 1
    first_calls = embedder.calls
    first_texts = list(embedder.texts)
    service.rebuild("repo_hash", root, policy)
    assert embedder.calls == first_calls
    assert embedder.texts == first_texts
    service.incremental("repo_hash", root, policy)
    assert embedder.calls == first_calls
    _ = EmbeddingPort


def test_swapping_embedder_identity_does_not_reuse_stale_vectors(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "hash-model",
        files={"src/mod.py": "STABLE_TOKEN = 1\n"},
    )
    policy = indexing_policy()
    first = _CountingEmbedder()
    service = IndexingService(
        paths,
        embeddings=first,
        embedding_identity=EmbeddingIdentity(kind="openai_compatible", model_id="small"),
    )
    service.rebuild("repo_model", root, policy)
    assert first.calls >= 1
    skipped = first.calls
    service.rebuild("repo_model", root, policy)
    assert first.calls == skipped
    service.incremental("repo_model", root, policy)
    assert first.calls == skipped

    second = _CountingEmbedder()
    swapped = IndexingService(
        paths,
        embeddings=second,
        embedding_identity=EmbeddingIdentity(kind="openai_compatible", model_id="large"),
    )
    swapped.incremental("repo_model", root, policy)
    assert second.calls >= 1


def test_switching_catalog_onnx_identities_reembeds(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "catalog-model",
        files={"src/mod.py": "STABLE_TOKEN = 1\n"},
    )
    policy = indexing_policy()
    first = _CountingEmbedder()
    service = IndexingService(
        paths,
        embeddings=first,
        embedding_identity=EmbeddingIdentity(kind="onnx", model_id="all-MiniLM-L6-v2"),
    )
    service.rebuild("repo_catalog", root, policy)
    skipped = first.calls
    assert skipped >= 1
    service.incremental("repo_catalog", root, policy)
    assert first.calls == skipped

    second = _CountingEmbedder()
    swapped = IndexingService(
        paths,
        embeddings=second,
        embedding_identity=EmbeddingIdentity(kind="onnx", model_id="BAAI/bge-small-en-v1.5"),
    )
    swapped.incremental("repo_catalog", root, policy)
    assert second.calls >= 1
    store = SqliteIndexStore(paths.cache / "indexes" / "repo_catalog" / "index.sqlite3")
    try:
        assert store.meta("embedding_model_id") == "BAAI/bge-small-en-v1.5"
    finally:
        store.close()


def test_identity_swap_on_partial_incremental_keeps_vectors_for_unchanged_paths(
    tmp_path: Path,
) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "identity-partial",
        files={
            "src/alpha.py": "ALPHA_STABLE = 1\n",
            "src/beta.py": "BETA_STABLE = 1\n",
        },
    )
    policy = indexing_policy()
    first = _CountingEmbedder()
    service = IndexingService(
        paths,
        embeddings=first,
        embedding_identity=EmbeddingIdentity(kind="openai_compatible", model_id="small"),
    )
    service.rebuild("repo_partial", root, policy)
    assert first.calls >= 1

    (root / "src/alpha.py").write_text("ALPHA_CHANGED = 2\n", encoding="utf-8")
    second = _CountingEmbedder()
    swapped = IndexingService(
        paths,
        embeddings=second,
        embedding_identity=EmbeddingIdentity(kind="openai_compatible", model_id="large"),
    )
    swapped.incremental("repo_partial", root, policy)

    store = SqliteIndexStore(paths.cache / "indexes" / "repo_partial" / "index.sqlite3")
    try:
        chunks = list(store.list_chunks())
        vector_ids = {
            str(row["chunk_id"])
            for row in store.connection().execute("SELECT chunk_id FROM vectors")
        }
        paths_with_vectors = {chunk.path for chunk in chunks if chunk.chunk_id in vector_ids}
        assert "src/alpha.py" in paths_with_vectors
        assert "src/beta.py" in paths_with_vectors
        assert {chunk.chunk_id for chunk in chunks} <= vector_ids
        assert store.meta("embedding_model_id") == "large"
    finally:
        store.close()

    joined = "\n".join(second.texts)
    assert "ALPHA_CHANGED" in joined
    assert "BETA_STABLE" in joined


def test_identity_swap_with_no_path_changes_reembeds_existing_chunks(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "identity-empty",
        files={
            "src/alpha.py": "ALPHA_STABLE = 1\n",
            "src/beta.py": "BETA_STABLE = 1\n",
        },
    )
    policy = indexing_policy()
    first = _CountingEmbedder()
    service = IndexingService(
        paths,
        embeddings=first,
        embedding_identity=EmbeddingIdentity(kind="openai_compatible", model_id="small"),
    )
    service.rebuild("repo_empty", root, policy)
    assert first.calls >= 1
    commit_tree(root, "empty")

    second = _CountingEmbedder()
    swapped = IndexingService(
        paths,
        embeddings=second,
        embedding_identity=EmbeddingIdentity(kind="openai_compatible", model_id="large"),
    )
    swapped.incremental("repo_empty", root, policy)

    store = SqliteIndexStore(paths.cache / "indexes" / "repo_empty" / "index.sqlite3")
    try:
        chunks = list(store.list_chunks())
        vector_ids = {
            str(row["chunk_id"])
            for row in store.connection().execute("SELECT chunk_id FROM vectors")
        }
        paths_with_vectors = {chunk.path for chunk in chunks if chunk.chunk_id in vector_ids}
        assert "src/alpha.py" in paths_with_vectors
        assert "src/beta.py" in paths_with_vectors
        assert {chunk.chunk_id for chunk in chunks} <= vector_ids
        assert store.meta("embedding_model_id") == "large"
    finally:
        store.close()

    joined = "\n".join(second.texts)
    assert second.calls >= 1
    assert "ALPHA_STABLE" in joined
    assert "BETA_STABLE" in joined


def test_changed_content_is_reembedded(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "hash-change",
        files={"src/mod.py": "BEFORE_TOKEN = 1\n"},
    )
    embedder = _CountingEmbedder()
    service = IndexingService(paths, embeddings=embedder)
    policy = indexing_policy()
    service.rebuild("repo_change", root, policy)
    before = embedder.calls
    (root / "src/mod.py").write_text("AFTER_TOKEN = 2\n", encoding="utf-8")
    service.incremental("repo_change", root, policy)
    assert embedder.calls > before
    assert any("AFTER_TOKEN" in text for text in embedder.texts)


def test_status_reports_progress_watch_and_idle_after_rebuild(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "progress",
        files={"src/mod.py": "def visible():\n    return 1\n"},
    )
    events: list[tuple[str, dict[str, object]]] = []
    service = IndexingService(
        paths,
        embeddings=_CountingEmbedder(),
        emit_event=lambda kind, payload: events.append((kind, dict(payload))),
    )
    status = service.rebuild("repo_progress", root, indexing_policy())
    assert status.state == "idle"
    assert status.watch_enabled is True
    assert status.files_total >= 1
    assert status.files_done == status.files_total
    assert status.chunks_embedded >= 1
    assert status.chunks_skipped >= 0
    assert status.last_activity_at
    assert "T" in status.last_activity_at
    kinds = [kind for kind, _payload in events]
    assert "index.progress" in kinds
    assert "index.idle" in kinds


class _BoomEmbedder(_CountingEmbedder):
    def __init__(self, *, fail: bool = True) -> None:
        super().__init__()
        self.fail = fail

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embed exploded")
        return super().embed(texts, kind=kind)


def test_rebuild_exception_resets_state_to_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(tmp_path / "boom-rebuild", files={"src/mod.py": "OK_TOKEN = 1\n"})
    policy = indexing_policy()
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    first = service.rebuild("repo_boom_rebuild", root, policy)
    assert first.state == "idle"

    def boom_scan(*_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("scan exploded")

    monkeypatch.setattr("kronos_engine.indexing.service.scan_with_working_tree", boom_scan)
    with pytest.raises(RuntimeError, match="scan exploded"):
        service.rebuild("repo_boom_rebuild", root, policy)
    status = service.status("repo_boom_rebuild", policy=policy)
    assert status.state == "idle"
    assert status.last_activity_at
    assert status.last_activity_at != first.last_activity_at


def test_incremental_exception_resets_state_to_idle(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(tmp_path / "boom-incr", files={"src/mod.py": "OK_TOKEN = 1\n"})
    policy = indexing_policy()
    embedder = _BoomEmbedder(fail=False)
    service = IndexingService(paths, embeddings=embedder)
    first = service.rebuild("repo_boom_incr", root, policy)
    assert first.state == "idle"
    embedder.fail = True
    (root / "src/mod.py").write_text("NEW_TOKEN = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="embed exploded"):
        service.incremental("repo_boom_incr", root, policy)
    status = service.status("repo_boom_incr", policy=policy)
    assert status.state == "idle"
    assert status.last_activity_at
    assert status.last_activity_at != first.last_activity_at


def test_targeted_incremental_leaves_other_dirty_paths_pending(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "targeted-dirty",
        files={
            "src/alpha.py": "ALPHA_OLD_TOKEN = 1\n",
            "src/beta.py": "BETA_OLD_TOKEN = 1\n",
        },
    )
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    policy = indexing_policy()
    service.rebuild("repo_targeted", root, policy)
    (root / "src/alpha.py").write_text("ALPHA_NEW_TOKEN = 2\n", encoding="utf-8")
    (root / "src/beta.py").write_text("BETA_NEW_TOKEN = 2\n", encoding="utf-8")
    service.incremental("repo_targeted", root, policy, paths=["src/alpha.py"])

    assert service.search("repo_targeted", "ALPHA_NEW_TOKEN", mode="sparse").items
    assert service.search("repo_targeted", "BETA_NEW_TOKEN", mode="sparse").items == ()
    assert service.search("repo_targeted", "BETA_OLD_TOKEN", mode="sparse").items
    _commit, indexed_dirty = service.indexed_revision("repo_targeted")
    assert "src/alpha.py" in indexed_dirty
    assert "src/beta.py" not in indexed_dirty

    remaining = sorted(set(list_dirty_paths(root)) - set(indexed_dirty))
    assert remaining == ["src/beta.py"]
    service.incremental("repo_targeted", root, policy, paths=remaining)
    assert service.search("repo_targeted", "BETA_NEW_TOKEN", mode="sparse").items
    assert service.search("repo_targeted", "BETA_OLD_TOKEN", mode="sparse").items == ()
    _commit, indexed_dirty = service.indexed_revision("repo_targeted")
    assert set(indexed_dirty) == {"src/alpha.py", "src/beta.py"}


def test_full_incremental_records_all_current_dirty_paths(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "full-dirty",
        files={
            "src/alpha.py": "ALPHA_OLD_TOKEN = 1\n",
            "src/beta.py": "BETA_OLD_TOKEN = 1\n",
        },
    )
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    policy = indexing_policy()
    service.rebuild("repo_full_dirty", root, policy)
    (root / "src/alpha.py").write_text("ALPHA_NEW_TOKEN = 2\n", encoding="utf-8")
    (root / "src/beta.py").write_text("BETA_NEW_TOKEN = 2\n", encoding="utf-8")
    service.incremental("repo_full_dirty", root, policy)
    _commit, indexed_dirty = service.indexed_revision("repo_full_dirty")
    assert set(indexed_dirty) == set(list_dirty_paths(root))
    assert set(indexed_dirty) == {"src/alpha.py", "src/beta.py"}


def test_watch_override_persists_outside_the_enrolled_tree(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "watch-flag",
        files={"src/mod.py": "WATCH_TOKEN = 1\n"},
    )
    before = {path.relative_to(root) for path in root.rglob("*") if path.is_file()}
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    policy = indexing_policy()
    service.rebuild("repo_watch", root, policy)
    status = service.set_watch_enabled("repo_watch", False, policy=policy)
    assert status.watch_enabled is False
    loaded = service.status("repo_watch", policy=policy)
    assert loaded.watch_enabled is False
    after = {path.relative_to(root) for path in root.rglob("*") if path.is_file()}
    assert after == before
