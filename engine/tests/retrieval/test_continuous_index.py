# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests.retrieval.support import indexing_policy, kronos_paths, write_and_commit
from tests.support.git_fixtures import init_git_repo

from kronos_engine.indexing.service import IndexingService
from kronos_engine.indexing.sparse import SqliteIndexStore
from kronos_engine.ports.embedding import EmbeddingPort


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
