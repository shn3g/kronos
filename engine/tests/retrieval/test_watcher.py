# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

from tests.retrieval.support import indexing_policy, kronos_paths, write_and_commit
from tests.support.git_fixtures import init_git_repo

from kronos_engine.domain.entities import EnrolledRepository, RepositoryId, RepositoryStatus
from kronos_engine.indexing.service import IndexingService
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
        debounce: int = 1600,
        stop_event: threading.Event | None = None,
        **_kwargs: object,
    ) -> Iterator[set[tuple[object, str]]]:
        assert debounce == record.policy.indexing.debounce_ms
        assert any(Path(item).resolve() == root.resolve() for item in watch_paths)
        while stop_event is None or not stop_event.is_set():
            if pending:
                yield pending.pop(0)
                continue
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
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if service.search(record.id.value, "LOOP_AFTER_TOKEN", mode="sparse").items:
            break
        time.sleep(0.05)
    watcher.stop()
    assert service.search(record.id.value, "LOOP_AFTER_TOKEN", mode="sparse").items
    assert not watcher.is_alive()


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
