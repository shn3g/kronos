# SPDX-License-Identifier: AGPL-3.0-or-later
"""Watch enrolled working trees and refresh the index. Fail-open; never writes git."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from kronos_engine.domain.entities import EnrolledRepository, RepositoryStatus
from kronos_engine.indexing.service import IndexingService

WatchChanges = set[tuple[Any, str]]
WatchFactory = Callable[..., Iterator[WatchChanges]]
RepoLister = Callable[[], Sequence[EnrolledRepository]]

_LOG = logging.getLogger("kronos.engine.index.watch")


def _watchfiles_watch(*paths: Path | str, **kwargs: Any) -> Iterator[WatchChanges]:
    from watchfiles import watch

    return watch(*paths, **kwargs)


class IndexWatcher:
    def __init__(
        self,
        *,
        list_repos: RepoLister,
        indexer: IndexingService | None = None,
        indexer_factory: Callable[[], IndexingService] | None = None,
        watch: WatchFactory | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if indexer_factory is not None:
            self._indexer_factory = indexer_factory
        elif indexer is not None:
            held = indexer
            self._indexer_factory = lambda: held
        else:
            raise ValueError("indexer or indexer_factory is required")
        self._list_repos = list_repos
        self._watch = watch or _watchfiles_watch
        self._log = logger or _LOG
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="kronos-index-watch", daemon=True
        )
        try:
            self._thread.start()
        except Exception:
            self._log.exception("index watcher failed to start")
            self._thread = None

    def stop(self) -> None:
        self._stop.set()
        worker = self._thread
        if worker is not None:
            worker.join(timeout=5.0)
        self._thread = None

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def apply_changes(
        self, repo: EnrolledRepository, changed: Iterable[Path | str]
    ) -> None:
        try:
            if not _repo_watch_enabled(repo, self._indexer_factory()):
                return
            root = Path(repo.realpath).resolve()
            relatives: list[str] = []
            git_only = False
            for raw in changed:
                path = Path(str(raw))
                try:
                    resolved = path.resolve()
                    relative = resolved.relative_to(root).as_posix()
                except ValueError:
                    continue
                if relative == ".":
                    continue
                if relative == ".git" or relative.startswith(".git/"):
                    git_only = True
                    continue
                relatives.append(relative)
            if relatives:
                self._indexer_factory().incremental(
                    repo.id.value, root, repo.policy, paths=relatives
                )
                return
            if git_only:
                self._indexer_factory().incremental(repo.id.value, root, repo.policy)
        except Exception:
            self._log.exception("index watch apply failed")

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    repos = self._watched_repos()
                    roots = tuple(sorted({Path(item.realpath).resolve() for item in repos}))
                    if not roots:
                        self._stop.wait(0.4)
                        continue
                    debounce = min(max(item.policy.indexing.debounce_ms, 0) for item in repos)
                    by_root = {Path(item.realpath).resolve(): item for item in repos}
                    by_id = {item.id.value: item for item in repos}
                    for changes in self._watch(
                        *roots,
                        debounce=debounce,
                        stop_event=self._stop,
                        yield_on_timeout=True,
                        rust_timeout=500,
                    ):
                        if self._stop.is_set():
                            break
                        current = tuple(
                            sorted(
                                {Path(item.realpath).resolve() for item in self._watched_repos()}
                            )
                        )
                        if current != roots:
                            break
                        if not changes:
                            continue
                        grouped: dict[str, list[Path]] = {}
                        for _kind, raw_path in changes:
                            repo = _repo_for(Path(raw_path).resolve(), by_root)
                            if repo is None:
                                continue
                            grouped.setdefault(repo.id.value, []).append(Path(raw_path))
                        for repo_id, changed_paths in grouped.items():
                            repo = by_id.get(repo_id)
                            if repo is None:
                                continue
                            self.apply_changes(repo, changed_paths)
                except Exception:
                    self._log.exception("index watch loop failed")
                    self._stop.wait(0.5)
        except Exception:
            self._log.exception("index watcher stopped")

    def _watched_repos(self) -> tuple[EnrolledRepository, ...]:
        try:
            records = tuple(self._list_repos())
        except Exception:
            self._log.exception("index watch list repos failed")
            return ()
        watched: list[EnrolledRepository] = []
        for record in records:
            if record.status is not RepositoryStatus.ACTIVE:
                continue
            if not _repo_watch_enabled(record, self._indexer_factory()):
                continue
            watched.append(record)
        return tuple(watched)


def _repo_watch_enabled(repo: EnrolledRepository, indexer: IndexingService) -> bool:
    try:
        return indexer.status(repo.id.value, policy=repo.policy).watch_enabled
    except Exception:
        return repo.policy.indexing.watch


def _repo_for(
    path: Path, by_root: dict[Path, EnrolledRepository]
) -> EnrolledRepository | None:
    current = path
    while True:
        found = by_root.get(current)
        if found is not None:
            return found
        if current.parent == current:
            return None
        current = current.parent
