# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from tests.retrieval.support import commit_tree, indexing_policy, kronos_paths, write_and_commit
from tests.support.git_fixtures import init_git_repo

from kronos_engine.domain.entities import EnrolledRepository, RepositoryId, RepositoryStatus
from kronos_engine.indexing.scanner import head_commit
from kronos_engine.indexing.service import IndexingService
from kronos_engine.indexing.sparse import SqliteIndexStore
from kronos_engine.indexing.watcher import IndexWatcher


class _CountingEmbedder:
    def available(self, kind: str) -> bool:
        _ = kind
        return True

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        _ = kind
        dim = 4
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * dim
            for index, char in enumerate(text.encode("utf-8")):
                vector[index % dim] += float(char)
            vectors.append(vector)
        return vectors


def _record(root: Path, repo_id: str = "repo_watch") -> EnrolledRepository:
    return EnrolledRepository(
        id=RepositoryId(repo_id),
        realpath=str(root.resolve()),
        origin=None,
        display_name=root.name,
        status=RepositoryStatus.ACTIVE,
        policy=indexing_policy(),
        enrolled_at="2020-01-01T00:00:00+00:00",
    )


def test_watcher_edit_commit_delete_refresh_targeted_paths(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "watched",
        files={
            "src/keep.py": "KEEP_TOKEN = 1\n",
            "src/edit.py": "BEFORE_EDIT = 1\n",
            "src/gone.py": "DELETE_ME = 1\n",
        },
    )
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    record = _record(root)
    service.rebuild(record.id.value, root, record.policy)
    watcher = IndexWatcher(list_repos=lambda: (record,), indexer=service)

    (root / "src/edit.py").write_text("AFTER_EDIT_TOKEN = 2\n", encoding="utf-8")
    watcher.apply_changes(record, (root / "src/edit.py",))
    assert service.search(record.id.value, "BEFORE_EDIT", mode="sparse").items == ()
    assert any(
        item.path.endswith("edit.py")
        for item in service.search(record.id.value, "AFTER_EDIT_TOKEN", mode="sparse").items
    )

    write_and_commit(root, {"src/edit.py": "AFTER_EDIT_TOKEN = 2\n"}, "commit edit")
    watcher.apply_changes(record, (root / "src/edit.py",))
    assert any(
        item.path.endswith("edit.py")
        for item in service.search(record.id.value, "AFTER_EDIT_TOKEN", mode="sparse").items
    )

    (root / "src/gone.py").unlink()
    watcher.apply_changes(record, (root / "src/gone.py",))
    assert service.search(record.id.value, "DELETE_ME", mode="sparse").items == ()
    assert any(
        item.path.endswith("keep.py")
        for item in service.search(record.id.value, "KEEP_TOKEN", mode="sparse").items
    )


def test_watcher_loop_processes_debounced_edits_and_stops_cleanly(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "loop",
        files={"src/mod.py": "LOOP_BEFORE = 1\n"},
    )
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    record = _record(root, "repo_loop")
    service.rebuild(record.id.value, root, record.policy)
    pending: list[set[tuple[object, str]]] = []
    released = threading.Event()

    def fake_watch(
        *watch_paths: Path | str,
        stop_event: threading.Event | None = None,
        **_kwargs: object,
    ) -> Iterator[set[tuple[object, str]]]:
        assert any(Path(item).resolve() == root.resolve() for item in watch_paths)
        while stop_event is None or not stop_event.is_set():
            if pending:
                yield pending.pop(0)
                continue
            yield set()
            if stop_event is None:
                return
            released.wait(0.05)

    watcher = IndexWatcher(
        list_repos=lambda: (record,),
        indexer=service,
        watch=fake_watch,
    )
    watcher.start()
    (root / "src/mod.py").write_text("LOOP_AFTER_TOKEN = 2\n", encoding="utf-8")
    pending.append({("modified", str(root / "src/mod.py"))})
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if service.search(record.id.value, "LOOP_AFTER_TOKEN", mode="sparse").items:
            break
        time.sleep(0.05)
    watcher.stop()
    assert service.search(record.id.value, "LOOP_AFTER_TOKEN", mode="sparse").items
    assert not watcher.is_alive()


def test_watcher_loop_indexes_git_commit_without_source_file_event(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(
        tmp_path / "git-only",
        files={"src/mod.py": "BASE_TOKEN = 1\n"},
    )
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    record = _record(root, "repo_git_only")
    first = service.rebuild(record.id.value, root, record.policy)
    (root / "src/mod.py").write_text("COMMITTED_FROM_DIRTY = 2\n", encoding="utf-8")
    service.incremental(record.id.value, root, record.policy)
    new_head = commit_tree(root, "commit dirty without rewriting the working tree")
    assert new_head != first.commit

    def fake_watch(
        *_watch_paths: Path | str,
        stop_event: threading.Event | None = None,
        **_kwargs: object,
    ) -> Iterator[set[tuple[object, str]]]:
        while stop_event is None or not stop_event.is_set():
            yield set()
            if stop_event is None:
                return
            stop_event.wait(0.02)

    watcher = IndexWatcher(list_repos=lambda: (record,), indexer=service, watch=fake_watch)
    watcher.start()
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if service.status(record.id.value).commit == new_head:
            break
        time.sleep(0.05)
    watcher.stop()
    assert service.status(record.id.value).commit == new_head
    store = SqliteIndexStore(paths.cache / "indexes" / record.id.value / "index.sqlite3")
    try:
        assert store.dirty_paths() == ()
    finally:
        store.close()


def test_watcher_honors_per_repo_debounce_ms(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    fast_root = init_git_repo(tmp_path / "fast", files={"src/a.py": "FAST_BEFORE = 1\n"})
    slow_root = init_git_repo(tmp_path / "slow", files={"src/b.py": "SLOW_BEFORE = 1\n"})
    inner = IndexingService(paths, embeddings=_CountingEmbedder())
    base = indexing_policy()
    fast = replace(
        _record(fast_root, "repo_fast"),
        policy=replace(base, indexing=replace(base.indexing, debounce_ms=40)),
    )
    slow = replace(
        _record(slow_root, "repo_slow"),
        policy=replace(base, indexing=replace(base.indexing, debounce_ms=180)),
    )
    inner.rebuild(fast.id.value, fast_root, fast.policy)
    inner.rebuild(slow.id.value, slow_root, slow.policy)
    applied: list[tuple[str, float]] = []

    class _TimedIndexer:
        def __getattr__(self, name: str) -> object:
            return getattr(inner, name)

        def incremental(
            self,
            repo_id: str,
            git_root: Path,
            policy: object,
            *,
            paths: Sequence[str] | None = None,
        ) -> object:
            applied.append((repo_id, time.monotonic()))
            return inner.incremental(repo_id, git_root, policy, paths=paths)

    change_at: dict[str, float] = {}

    def fake_watch(
        *_watch_paths: Path | str,
        debounce: int = 1600,
        step: int = 50,
        stop_event: threading.Event | None = None,
        **_kwargs: object,
    ) -> Iterator[set[tuple[object, str]]]:
        _ = debounce, step
        change_at["t"] = time.monotonic()
        yield {
            ("modified", str(fast_root / "src/a.py")),
            ("modified", str(slow_root / "src/b.py")),
        }
        while stop_event is None or not stop_event.is_set():
            yield set()
            if stop_event is None:
                return
            stop_event.wait(0.02)

    (fast_root / "src/a.py").write_text("FAST_AFTER_TOKEN = 2\n", encoding="utf-8")
    (slow_root / "src/b.py").write_text("SLOW_AFTER_TOKEN = 2\n", encoding="utf-8")
    watcher = IndexWatcher(
        list_repos=lambda: (fast, slow),
        indexer=_TimedIndexer(),  # type: ignore[arg-type]
        watch=fake_watch,
    )
    watcher.start()
    deadline = time.time() + 3.0
    while time.time() < deadline:
        ids = {repo_id for repo_id, _when in applied}
        if ids >= {fast.id.value, slow.id.value}:
            break
        time.sleep(0.02)
    watcher.stop()
    fast_times = [when for repo_id, when in applied if repo_id == fast.id.value]
    slow_times = [when for repo_id, when in applied if repo_id == slow.id.value]
    assert fast_times and slow_times
    origin = change_at["t"]
    fast_delay = min(fast_times) - origin
    slow_delay = min(slow_times) - origin
    assert slow_delay >= 0.15
    assert fast_delay < slow_delay


def test_idle_ticks_do_not_invoke_indexer_factory_each_pump(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(tmp_path / "factory-idle", files={"src/mod.py": "IDLE_TOKEN = 1\n"})
    service = IndexingService(paths, embeddings=_CountingEmbedder())
    record = replace(
        _record(root, "repo_factory_idle"),
        policy=replace(
            indexing_policy(),
            indexing=replace(indexing_policy().indexing, debounce_ms=40),
        ),
    )
    service.rebuild(record.id.value, root, record.policy)
    factory_calls = {"n": 0}

    def factory() -> IndexingService:
        factory_calls["n"] += 1
        return service

    ticks = {"n": 0}
    pending: list[set[tuple[object, str]]] = []
    started = threading.Event()

    def fake_watch(
        *_watch_paths: Path | str,
        stop_event: threading.Event | None = None,
        **_kwargs: object,
    ) -> Iterator[set[tuple[object, str]]]:
        while stop_event is None or not stop_event.is_set():
            started.set()
            ticks["n"] += 1
            if pending:
                yield pending.pop(0)
                continue
            yield set()
            if stop_event is None:
                return
            stop_event.wait(0.02)

    watcher = IndexWatcher(
        list_repos=lambda: (record,),
        indexer=service,
        indexer_factory=factory,
        watch=fake_watch,
    )
    watcher.start()
    assert started.wait(1.0)
    deadline = time.time() + 0.4
    while time.time() < deadline:
        if ticks["n"] >= 8:
            break
        time.sleep(0.02)
    assert ticks["n"] >= 8
    idle_calls = factory_calls["n"]
    assert idle_calls < ticks["n"]
    assert idle_calls == 0

    (root / "src/mod.py").write_text("FACTORY_REFRESH_TOKEN = 2\n", encoding="utf-8")
    pending.append({("modified", str(root / "src/mod.py"))})
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if service.search(record.id.value, "FACTORY_REFRESH_TOKEN", mode="sparse").items:
            break
        time.sleep(0.02)
    watcher.stop()
    assert service.search(record.id.value, "FACTORY_REFRESH_TOKEN", mode="sparse").items
    assert factory_calls["n"] >= 1

    solo_calls = {"n": 0}

    def solo_factory() -> IndexingService:
        solo_calls["n"] += 1
        return service

    solo = IndexWatcher(list_repos=lambda: (record,), indexer_factory=solo_factory)
    origin = time.monotonic()
    for step in range(10):
        repos = solo._watched_repos()
        solo._poll_commits(repos, origin + step * 0.05)
    assert solo_calls["n"] <= 1
    assert solo_calls["n"] < 10


def test_commit_poll_compares_revision_without_status_or_list_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = kronos_paths(tmp_path)
    root = init_git_repo(tmp_path / "poll", files={"src/mod.py": "POLL_TOKEN = 1\n"})
    inner = IndexingService(paths, embeddings=_CountingEmbedder())
    record = _record(root, "repo_poll")
    inner.rebuild(record.id.value, root, record.policy)
    status_calls = 0
    list_chunks_calls = 0
    head_times: list[float] = []
    real_head = head_commit

    def wrapped_head(git_root: Path) -> str:
        head_times.append(time.monotonic())
        return real_head(git_root)

    monkeypatch.setattr("kronos_engine.indexing.watcher.head_commit", wrapped_head)

    class _Probe:
        def status(self, *args: object, **kwargs: object) -> object:
            nonlocal status_calls
            status_calls += 1
            return inner.status(*args, **kwargs)

        def list_chunks(self, *args: object, **kwargs: object) -> object:
            nonlocal list_chunks_calls
            list_chunks_calls += 1
            return inner.list_chunks(*args, **kwargs)

        def __getattr__(self, name: str) -> object:
            return getattr(inner, name)

    ticks = {"n": 0}
    started = threading.Event()

    def fake_watch(
        *_watch_paths: Path | str,
        stop_event: threading.Event | None = None,
        **_kwargs: object,
    ) -> Iterator[set[tuple[object, str]]]:
        while stop_event is None or not stop_event.is_set():
            started.set()
            ticks["n"] += 1
            yield set()
            if stop_event is None:
                return
            stop_event.wait(0.02)

    watcher = IndexWatcher(
        list_repos=lambda: (record,),
        indexer=_Probe(),  # type: ignore[arg-type]
        watch=fake_watch,
    )
    watcher.start()
    assert started.wait(1.0)
    deadline = time.time() + 0.4
    while time.time() < deadline:
        if ticks["n"] >= 8:
            break
        time.sleep(0.02)
    watcher.stop()
    assert ticks["n"] >= 8
    assert status_calls == 0
    assert list_chunks_calls == 0
    assert 1 <= len(head_times) <= 2


def test_watcher_errors_fail_open(tmp_path: Path) -> None:
    paths = kronos_paths(tmp_path)

    def boom_watch(*_args: object, **_kwargs: object) -> Sequence[object]:
        raise RuntimeError("watch exploded")

    watcher = IndexWatcher(
        list_repos=lambda: (),
        indexer=IndexingService(paths, embeddings=_CountingEmbedder()),
        watch=boom_watch,  # type: ignore[arg-type]
    )
    watcher.start()
    watcher.stop()
    assert not watcher.is_alive()
