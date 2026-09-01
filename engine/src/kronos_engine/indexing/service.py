# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-repository hybrid index. Cache only; never writes the enrolled git tree."""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kronos_engine.adapters.embeddings.local import LocalEmbeddingAdapter
from kronos_engine.config.paths import KronosPaths
from kronos_engine.domain.policy import RepositoryPolicy
from kronos_engine.indexing.chunks import chunk_text
from kronos_engine.indexing.context import ContextPack, assemble_context, repo_map
from kronos_engine.indexing.dense import EmbedStats, drop_vectors, search_dense, upsert_embeddings
from kronos_engine.indexing.fusion import reciprocal_rank_fusion
from kronos_engine.indexing.graph import build_relations, expand_paths
from kronos_engine.indexing.scanner import (
    GitReadError,
    diff_paths,
    head_commit,
    list_dirty_paths,
    scan_blob_path,
    scan_with_working_tree,
    scan_working_tree_path,
)
from kronos_engine.indexing.sparse import SqliteIndexStore
from kronos_engine.ports.embedding import EmbeddingIdentity, EmbeddingPort
from kronos_engine.ports.index_store import IndexedChunk

INDEX_STATE_IDLE = "idle"
INDEX_STATE_SCANNING = "scanning"
INDEX_STATE_EMBEDDING = "embedding"

EventEmitter = Callable[[str, Mapping[str, object]], None]

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_LOG = logging.getLogger("kronos.engine.index")


@dataclass(frozen=True, slots=True)
class IndexStatus:
    repository_id: str
    commit: str | None
    chunk_count: int
    dense_available: bool
    index_path: str
    disk_bytes: int
    ready: bool
    state: str
    files_done: int
    files_total: int
    chunks_embedded: int
    chunks_skipped: int
    last_activity_at: str | None
    watch_enabled: bool


class IndexingService:
    def __init__(
        self,
        paths: KronosPaths,
        embeddings: EmbeddingPort | None = None,
        emit_event: EventEmitter | None = None,
        *,
        embedding_identity: EmbeddingIdentity | None = None,
    ) -> None:
        self._paths = paths
        self._embeddings: EmbeddingPort = embeddings or LocalEmbeddingAdapter(
            paths.cache / "models"
        )
        self._emit_event = emit_event
        self._embedding_identity = embedding_identity

    def rebuild(self, repo_id: str, git_root: Path, policy: RepositoryPolicy) -> IndexStatus:
        with _repo_lock(repo_id):
            return self._rebuild(repo_id, git_root, policy)

    def incremental(
        self,
        repo_id: str,
        git_root: Path,
        policy: RepositoryPolicy,
        *,
        paths: Sequence[str] | None = None,
    ) -> IndexStatus:
        with _repo_lock(repo_id):
            return self._incremental(repo_id, git_root, policy, paths=paths)

    def set_watch_enabled(
        self,
        repo_id: str,
        enabled: bool,
        *,
        policy: RepositoryPolicy | None = None,
    ) -> IndexStatus:
        with _repo_lock(repo_id):
            store = SqliteIndexStore(self._index_dir(repo_id) / "index.sqlite3")
            try:
                store.set_meta("watch_enabled", "true" if enabled else "false")
                return self._status(repo_id, store, policy=policy)
            finally:
                store.close()

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

    def watch_enabled(self, repo_id: str, *, policy: RepositoryPolicy | None = None) -> bool:
        db_path = self._index_dir(repo_id) / "index.sqlite3"
        if not db_path.is_file():
            return _watch_enabled(None, policy)
        store = SqliteIndexStore(db_path)
        try:
            return _watch_enabled(store.meta("watch_enabled"), policy)
        finally:
            store.close()

    def indexed_revision(self, repo_id: str) -> tuple[str | None, tuple[str, ...]]:
        db_path = self._index_dir(repo_id) / "index.sqlite3"
        if not db_path.is_file():
            return None, ()
        store = SqliteIndexStore(db_path)
        try:
            return store.indexed_commit(), store.dirty_paths()
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

    def status(self, repo_id: str, *, policy: RepositoryPolicy | None = None) -> IndexStatus:
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
                state=INDEX_STATE_IDLE,
                files_done=0,
                files_total=0,
                chunks_embedded=0,
                chunks_skipped=0,
                last_activity_at=None,
                watch_enabled=_watch_enabled(None, policy),
            )
        try:
            store = SqliteIndexStore(db_path)
        except sqlite3.Error as error:
            raise RuntimeError("corrupt cache") from error
        try:
            return self._status(repo_id, store, policy=policy)
        except sqlite3.Error as error:
            raise RuntimeError("corrupt cache") from error
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

    def _rebuild(self, repo_id: str, git_root: Path, policy: RepositoryPolicy) -> IndexStatus:
        root = git_root.resolve()
        store = self._open(repo_id, root)
        try:
            commit = head_commit(root)
            self._mark(store, repo_id, INDEX_STATE_SCANNING, files_done=0, files_total=0)
            scanned = scan_with_working_tree(root, policy, commit=commit)
            chunks: list[IndexedChunk] = []
            total = len(scanned)
            for index, item in enumerate(scanned, start=1):
                chunks.extend(chunk_text(item, commit=commit))
                if index == 1 or index == total or index % 25 == 0:
                    self._mark(
                        store,
                        repo_id,
                        INDEX_STATE_SCANNING,
                        files_done=index,
                        files_total=total,
                        emit=index == total,
                    )
            relations = build_relations(chunks)
            store.replace_all(chunks, relations)
            self._mark(
                store,
                repo_id,
                INDEX_STATE_EMBEDDING,
                files_done=total,
                files_total=total,
            )
            stats = self._embed_chunks(store, chunks)
            store.set_indexed_commit(commit)
            store.set_dirty_paths(list_dirty_paths(root))
            self._mark(
                store,
                repo_id,
                INDEX_STATE_IDLE,
                files_done=total,
                files_total=total,
                chunks_embedded=stats.embedded,
                chunks_skipped=stats.skipped,
                event_kind="index.idle",
            )
            return self._status(repo_id, store, policy=policy)
        finally:
            self._idle_if_busy(store, repo_id)
            store.close()

    def _incremental(
        self,
        repo_id: str,
        git_root: Path,
        policy: RepositoryPolicy,
        *,
        paths: Sequence[str] | None,
    ) -> IndexStatus:
        root = git_root.resolve()
        directory = self._index_dir(repo_id)
        db_path = directory / "index.sqlite3"
        if not db_path.is_file():
            return self._rebuild(repo_id, root, policy)
        store = self._open(repo_id, root)
        try:
            old = store.indexed_commit()
            new = head_commit(root)
            current_dirty = list_dirty_paths(root)
            stored_dirty = store.dirty_paths()
            targeted = tuple(_posix(path) for path in paths or () if _posix(path))
            if (
                old is not None
                and old == new
                and not current_dirty
                and not stored_dirty
                and not targeted
            ):
                if self._backend_changed(store):
                    self._mark(
                        store,
                        repo_id,
                        INDEX_STATE_EMBEDDING,
                        files_done=0,
                        files_total=0,
                    )
                    stats = self._embed_chunks(store, list(store.list_chunks()))
                    self._mark(
                        store,
                        repo_id,
                        INDEX_STATE_IDLE,
                        files_done=0,
                        files_total=0,
                        chunks_embedded=stats.embedded,
                        chunks_skipped=stats.skipped,
                        event_kind="index.idle",
                    )
                return self._status(repo_id, store, policy=policy)
            refresh: set[str] = set(targeted)
            commit_diff: tuple[tuple[str, str, str], ...] | None
            if old is not None and old != new:
                try:
                    commit_diff = diff_paths(root, old, new)
                except GitReadError:
                    commit_diff = None
            else:
                commit_diff = ()
            if commit_diff is None:
                rebuild = True
            else:
                rebuild = False
                for status, path, renamed_from in commit_diff:
                    if status == "D":
                        refresh.add(path)
                        continue
                    if status == "R":
                        refresh.add(renamed_from)
                    refresh.add(path)
            if rebuild:
                pass
            else:
                if not targeted:
                    refresh.update(current_dirty)
                    refresh.update(stored_dirty)
                if not refresh:
                    store.set_indexed_commit(new)
                    store.set_dirty_paths(current_dirty)
                    return self._status(repo_id, store, policy=policy)
                self._mark(
                    store,
                    repo_id,
                    INDEX_STATE_SCANNING,
                    files_done=0,
                    files_total=len(refresh),
                )
                changed_chunks: list[IndexedChunk] = []
                dirty_set = set(current_dirty)
                for index, posix in enumerate(sorted(refresh), start=1):
                    changed_chunks.extend(
                        self._refresh_path(store, root, policy, new, posix, dirty_set)
                    )
                    if index == 1 or index == len(refresh) or index % 25 == 0:
                        self._mark(
                            store,
                            repo_id,
                            INDEX_STATE_SCANNING,
                            files_done=index,
                            files_total=len(refresh),
                            emit=index == len(refresh),
                        )
                store.replace_relations(build_relations(store.list_chunks()))
                self._mark(
                    store,
                    repo_id,
                    INDEX_STATE_EMBEDDING,
                    files_done=len(refresh),
                    files_total=len(refresh),
                )
                stats = self._embed_chunks(store, changed_chunks)
                store.set_indexed_commit(new)
                if targeted:
                    refreshed = set(refresh)
                    store.set_dirty_paths(
                        sorted((set(stored_dirty) - refreshed) | (refreshed & set(current_dirty)))
                    )
                else:
                    store.set_dirty_paths(current_dirty)
                self._mark(
                    store,
                    repo_id,
                    INDEX_STATE_IDLE,
                    files_done=len(refresh),
                    files_total=len(refresh),
                    chunks_embedded=stats.embedded,
                    chunks_skipped=stats.skipped,
                    event_kind="index.idle",
                )
                return self._status(repo_id, store, policy=policy)
        finally:
            self._idle_if_busy(store, repo_id)
            store.close()
        return self._rebuild(repo_id, root, policy)

    def _refresh_path(
        self,
        store: SqliteIndexStore,
        root: Path,
        policy: RepositoryPolicy,
        commit: str,
        posix: str,
        dirty: set[str],
    ) -> list[IndexedChunk]:
        if posix in dirty:
            scanned = scan_working_tree_path(root, policy, posix)
        else:
            scanned = scan_blob_path(root, policy, posix, commit=commit)
        if scanned is None:
            store.delete_paths([posix])
            return []
        chunked = list(chunk_text(scanned, commit=commit))
        store.replace_path_chunks(posix, chunked)
        return chunked

    def _embed_chunks(self, store: SqliteIndexStore, chunks: Sequence[IndexedChunk]) -> EmbedStats:
        pending: Sequence[IndexedChunk] = chunks
        if self._embedding_identity is not None and self._backend_changed(store):
            drop_vectors(store.connection())
            pending = list(store.list_chunks())
        stats = upsert_embeddings(store.connection(), pending, self._embeddings)
        identity = self._embedding_identity
        if identity is not None:
            store.set_meta("embedding_kind", identity.kind)
            store.set_meta("embedding_model_id", identity.model_id)
        return stats

    def _backend_changed(self, store: SqliteIndexStore) -> bool:
        identity = self._embedding_identity
        if identity is None:
            return False
        stored_kind = store.meta("embedding_kind")
        stored_model = store.meta("embedding_model_id")
        if stored_kind is None and stored_model is None:
            row = store.connection().execute("SELECT 1 FROM vectors LIMIT 1").fetchone()
            return row is not None
        return stored_kind != identity.kind or stored_model != identity.model_id

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

    def _status(
        self,
        repo_id: str,
        store: SqliteIndexStore,
        *,
        policy: RepositoryPolicy | None = None,
    ) -> IndexStatus:
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
            state=_state_meta(store.meta("index_state")),
            files_done=_int_meta(store.meta("files_done")),
            files_total=_int_meta(store.meta("files_total")),
            chunks_embedded=_int_meta(store.meta("chunks_embedded")),
            chunks_skipped=_int_meta(store.meta("chunks_skipped")),
            last_activity_at=store.meta("last_activity_at"),
            watch_enabled=_watch_enabled(store.meta("watch_enabled"), policy),
        )

    def _dense_available(self) -> bool:
        return self._embeddings.available("code") or self._embeddings.available("document")

    def _open(self, repo_id: str, git_root: Path) -> SqliteIndexStore:
        directory = self._index_dir(repo_id)
        _assert_outside(directory, git_root)
        return SqliteIndexStore(directory / "index.sqlite3")

    def _index_dir(self, repo_id: str) -> Path:
        return self._paths.cache / "indexes" / repo_id

    def _idle_if_busy(self, store: SqliteIndexStore, repo_id: str) -> None:
        try:
            state = _state_meta(store.meta("index_state"))
            if state in {INDEX_STATE_SCANNING, INDEX_STATE_EMBEDDING}:
                self._mark(store, repo_id, INDEX_STATE_IDLE, event_kind="index.idle")
        except Exception:
            _LOG.exception("index failed to reset idle state")

    def _mark(
        self,
        store: SqliteIndexStore,
        repo_id: str,
        state: str,
        *,
        files_done: int | None = None,
        files_total: int | None = None,
        chunks_embedded: int | None = None,
        chunks_skipped: int | None = None,
        emit: bool = True,
        event_kind: str = "index.progress",
    ) -> None:
        stamp = datetime.now(tz=UTC).isoformat()
        store.set_meta("index_state", state)
        store.set_meta("last_activity_at", stamp)
        if files_done is not None:
            store.set_meta("files_done", str(files_done))
        if files_total is not None:
            store.set_meta("files_total", str(files_total))
        if chunks_embedded is not None:
            store.set_meta("chunks_embedded", str(chunks_embedded))
        if chunks_skipped is not None:
            store.set_meta("chunks_skipped", str(chunks_skipped))
        if not emit:
            return
        payload: dict[str, object] = {
            "repository_id": repo_id,
            "state": state,
            "files_done": _int_meta(store.meta("files_done")),
            "files_total": _int_meta(store.meta("files_total")),
            "chunks_embedded": _int_meta(store.meta("chunks_embedded")),
            "chunks_skipped": _int_meta(store.meta("chunks_skipped")),
            "last_activity_at": stamp,
        }
        self._emit(event_kind, payload)

    def _emit(self, kind: str, payload: Mapping[str, object]) -> None:
        if self._emit_event is None:
            return
        try:
            self._emit_event(kind, payload)
        except Exception:
            _LOG.exception("index event emit failed")


def _repo_lock(repo_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(repo_id, threading.Lock())


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _watch_enabled(override: str | None, policy: RepositoryPolicy | None) -> bool:
    if override == "true":
        return True
    if override == "false":
        return False
    if policy is not None:
        return policy.indexing.watch
    return True


def _state_meta(raw: str | None) -> str:
    if raw in {INDEX_STATE_IDLE, INDEX_STATE_SCANNING, INDEX_STATE_EMBEDDING}:
        return raw
    return INDEX_STATE_IDLE


def _int_meta(raw: str | None) -> int:
    if raw is None:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _assert_outside(target: Path, enrolled_root: Path) -> None:
    resolved_target = target.resolve()
    resolved_root = enrolled_root.resolve()
    if resolved_target == resolved_root or resolved_root in resolved_target.parents:
        raise RuntimeError("indexes must stay outside the enrolled git tree")


def _disk_bytes(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
