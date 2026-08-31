# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-repository hybrid index. Cache only; never writes the enrolled git tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kronos_engine.adapters.embeddings.local import LocalEmbeddingAdapter
from kronos_engine.config.paths import KronosPaths
from kronos_engine.domain.policy import RepositoryPolicy
from kronos_engine.indexing.chunks import chunk_text
from kronos_engine.indexing.context import ContextPack, assemble_context, repo_map
from kronos_engine.indexing.dense import search_dense, upsert_embeddings
from kronos_engine.indexing.fusion import reciprocal_rank_fusion
from kronos_engine.indexing.graph import build_relations, expand_paths
from kronos_engine.indexing.scanner import GitReadError, diff_paths, head_commit, scan_repository
from kronos_engine.indexing.sparse import SqliteIndexStore
from kronos_engine.ports.embedding import EmbeddingPort
from kronos_engine.ports.index_store import IndexedChunk


@dataclass(frozen=True, slots=True)
class IndexStatus:
    repository_id: str
    commit: str | None
    chunk_count: int
    dense_available: bool
    index_path: str
    disk_bytes: int
    ready: bool


class IndexingService:
    def __init__(self, paths: KronosPaths, embeddings: EmbeddingPort | None = None) -> None:
        self._paths = paths
        self._embeddings: EmbeddingPort = embeddings or LocalEmbeddingAdapter(
            paths.cache / "models"
        )

    def rebuild(self, repo_id: str, git_root: Path, policy: RepositoryPolicy) -> IndexStatus:
        root = git_root.resolve()
        store = self._open(repo_id, root)
        try:
            commit = head_commit(root)
            scanned = scan_repository(root, policy, commit=commit)
            chunks: list[IndexedChunk] = []
            for item in scanned:
                chunks.extend(chunk_text(item, commit=commit))
            relations = build_relations(chunks)
            store.replace_all(chunks, relations)
            if chunks:
                upsert_embeddings(store.connection(), chunks, self._embeddings)
            store.set_indexed_commit(commit)
            return self._status(repo_id, store)
        finally:
            store.close()

    def incremental(self, repo_id: str, git_root: Path, policy: RepositoryPolicy) -> IndexStatus:
        root = git_root.resolve()
        directory = self._index_dir(repo_id)
        db_path = directory / "index.sqlite3"
        if not db_path.is_file():
            return self.rebuild(repo_id, root, policy)
        store = self._open(repo_id, root)
        try:
            old = store.indexed_commit()
            new = head_commit(root)
            if old is not None and old == new:
                return self._status(repo_id, store)
            if old is not None:
                try:
                    changes = diff_paths(root, old, new)
                except GitReadError:
                    pass
                else:
                    scanned = {
                        item.path: item for item in scan_repository(root, policy, commit=new)
                    }
                    changed_chunks: list[IndexedChunk] = []
                    for status, path, renamed_from in changes:
                        if status == "D":
                            store.delete_paths([path])
                            continue
                        if status == "R":
                            store.delete_paths([renamed_from, path])
                        else:
                            store.delete_paths([path])
                        current = scanned.get(path)
                        if current is None:
                            continue
                        chunked = chunk_text(current, commit=new)
                        store.upsert(chunked)
                        changed_chunks.extend(chunked)
                    store.replace_relations(build_relations(store.list_chunks()))
                    if changed_chunks:
                        upsert_embeddings(store.connection(), changed_chunks, self._embeddings)
                    store.set_indexed_commit(new)
                    return self._status(repo_id, store)
        finally:
            store.close()
        return self.rebuild(repo_id, root, policy)

    def search(
        self,
        repo_id: str,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 20,
        budget_tokens: int = 4000,
    ) -> ContextPack:
        db_path = self._index_dir(repo_id) / "index.sqlite3"
        if not db_path.is_file() or query.strip() == "":
            return ContextPack(items=())
        store = SqliteIndexStore(db_path)
        try:
            sparse_ids = list(store.search_sparse(query, limit=limit * 4))
            sources: dict[str, list[str]] = {chunk_id: ["sparse"] for chunk_id in sparse_ids}
            rankings: list[list[str]] = [sparse_ids]
            if mode == "hybrid":
                graph_ids = self._graph_ranking(store, sparse_ids, limit=limit * 2)
                if graph_ids:
                    rankings.append(graph_ids)
                    for chunk_id in graph_ids:
                        sources.setdefault(chunk_id, []).append("graph")
                dense_ids = self._dense_ranking(store, query, limit=limit * 2)
                if dense_ids:
                    rankings.append(list(dense_ids))
                    for chunk_id in dense_ids:
                        sources.setdefault(chunk_id, []).append("dense")
            ordered = reciprocal_rank_fusion(tuple(rankings)) if mode == "hybrid" else sparse_ids
            packed: list[tuple[IndexedChunk, tuple[str, ...]]] = []
            seen_paths: set[str] = set()
            for chunk_id in ordered:
                chunk = store.get_chunk(chunk_id)
                if chunk is None or chunk.path in seen_paths:
                    continue
                seen_paths.add(chunk.path)
                labels = tuple(dict.fromkeys(sources.get(chunk_id, ("sparse",))))
                packed.append((chunk, labels))
                if len(packed) >= limit:
                    break
            return assemble_context(packed, budget_tokens=budget_tokens)
        finally:
            store.close()

    def list_chunks(self, repo_id: str) -> tuple[IndexedChunk, ...]:
        db_path = self._index_dir(repo_id) / "index.sqlite3"
        if not db_path.is_file():
            return ()
        store = SqliteIndexStore(db_path)
        try:
            return tuple(store.list_chunks())
        finally:
            store.close()

    def status(self, repo_id: str) -> IndexStatus:
        db_path = self._index_dir(repo_id) / "index.sqlite3"
        if not db_path.is_file():
            return IndexStatus(
                repository_id=repo_id,
                commit=None,
                chunk_count=0,
                dense_available=self._dense_available(),
                index_path=str(self._index_dir(repo_id)),
                disk_bytes=0,
                ready=False,
            )
        store = SqliteIndexStore(db_path)
        try:
            return self._status(repo_id, store)
        finally:
            store.close()

    def repo_map(self, repo_id: str, *, budget_tokens: int = 2000) -> str:
        db_path = self._index_dir(repo_id) / "index.sqlite3"
        if not db_path.is_file():
            return ""
        store = SqliteIndexStore(db_path)
        try:
            return repo_map(store.list_chunks(), budget_tokens=budget_tokens)
        finally:
            store.close()

    def _graph_ranking(
        self, store: SqliteIndexStore, sparse_ids: list[str], *, limit: int
    ) -> list[str]:
        seed_paths = []
        for chunk_id in sparse_ids:
            chunk = store.get_chunk(chunk_id)
            if chunk is not None:
                seed_paths.append(chunk.path)
        extra = expand_paths(seed_paths, store.list_relations(), limit=limit)
        ids: list[str] = []
        for path in extra:
            chunks = store.chunks_for_path(path)
            if chunks:
                ids.append(chunks[0].chunk_id)
        return ids

    def _dense_ranking(self, store: SqliteIndexStore, query: str, *, limit: int) -> tuple[str, ...]:
        ids: list[str] = []
        for kind in ("code", "document"):
            if not self._embeddings.available(kind):
                continue
            vectors = self._embeddings.embed([query], kind=kind)
            if not vectors:
                continue
            ids.extend(search_dense(store.connection(), vectors[0], kind=kind, limit=limit))
        return tuple(dict.fromkeys(ids))

    def _status(self, repo_id: str, store: SqliteIndexStore) -> IndexStatus:
        chunks = store.list_chunks()
        directory = self._index_dir(repo_id)
        return IndexStatus(
            repository_id=repo_id,
            commit=store.indexed_commit(),
            chunk_count=len(chunks),
            dense_available=self._dense_available(),
            index_path=str(directory),
            disk_bytes=_disk_bytes(directory),
            ready=len(chunks) > 0,
        )

    def _dense_available(self) -> bool:
        return self._embeddings.available("code") or self._embeddings.available("document")

    def _open(self, repo_id: str, git_root: Path) -> SqliteIndexStore:
        directory = self._index_dir(repo_id)
        _assert_outside(directory, git_root)
        return SqliteIndexStore(directory / "index.sqlite3")

    def _index_dir(self, repo_id: str) -> Path:
        return self._paths.cache / "indexes" / repo_id


def _assert_outside(target: Path, enrolled_root: Path) -> None:
    resolved_target = target.resolve()
    resolved_root = enrolled_root.resolve()
    if resolved_target == resolved_root or resolved_root in resolved_target.parents:
        raise RuntimeError("indexes must stay outside the enrolled git tree")


def _disk_bytes(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
