# SPDX-License-Identifier: AGPL-3.0-or-later
"""Watch enrolled working trees and refresh the index. Fail-open; never writes git."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kronos_engine.domain.entities import EnrolledRepository, RepositoryStatus
from kronos_engine.indexing.scanner import head_commit, list_dirty_paths
from kronos_engine.indexing.service import IndexingService

WatchChanges = set[tuple[Any, str]]
WatchFactory = Callable[..., Iterator[WatchChanges]]
RepoLister = Callable[[], Sequence[EnrolledRepository]]

_LOG = logging.getLogger("kronos.engine.index.watch")
_PUMP_MS = 50
_COMMIT_POLL_MIN_MS = 1000
_GIT_WATCH_NAMES = frozenset({"HEAD", "index", "packed-refs"})
_DEFAULT_IGNORE_DIRS = frozenset(
    {
        "__pycache__",
        ".hg",
        ".svn",
        ".tox",
        ".venv",
        ".idea",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".hypothesis",
    }
)


def _watchfiles_watch(*paths: Path | str, **kwargs: Any) -> Iterator[WatchChanges]:
    from watchfiles import watch

    kwargs.setdefault("watch_filter", index_watch_filter)
    return watch(*paths, **kwargs)


def index_watch_filter(_change: object, path: str) -> bool:
    """Keep working-tree files plus git HEAD/index/refs; drop the rest of `.git`."""
    posix = path.replace("\\", "/")
    parts = posix.split("/")
    if ".git" in parts:
        rest = parts[parts.index(".git") + 1 :]
        if not rest:
            return True
        if rest[0] in _GIT_WATCH_NAMES:
            return True
        return rest[0] == "refs"
    return not any(part in _DEFAULT_IGNORE_DIRS for part in parts)


@dataclass
class _Pending:
    paths: list[Path] = field(default_factory=list)
    last_at: float = 0.0


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
        self._meta_indexer = indexer
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
        self._pending: dict[str, _Pending] = {}
        self._commit_poll_at: dict[str, float] = {}
        self._probes: dict[str, IndexingService] = {}

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
        self._pending.clear()
        self._commit_poll_at.clear()
        self._probes.clear()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def apply_changes(
        self, repo: EnrolledRepository, changed: Iterable[Path | str]
    ) -> None:
        try:
            if not _repo_watch_enabled(repo, self._probe(repo.id.value)):
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
                    by_root = {Path(item.realpath).resolve(): item for item in repos}
                    by_id = {item.id.value: item for item in repos}
                    for changes in self._watch(
                        *roots,
                        debounce=_PUMP_MS,
                        step=_PUMP_MS,
                        stop_event=self._stop,
                        yield_on_timeout=True,
                        rust_timeout=_PUMP_MS,
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
                        repos = tuple(by_id[key] for key in by_id)
                        now = time.monotonic()
                        if changes:
                            grouped: dict[str, list[Path]] = {}
                            for _kind, raw_path in changes:
                                repo = _repo_for(Path(raw_path).resolve(), by_root)
                                if repo is None:
                                    continue
                                grouped.setdefault(repo.id.value, []).append(Path(raw_path))
                            for repo_id, changed_paths in grouped.items():
                                self._note(repo_id, changed_paths, now)
                        self._flush_due(by_id, now)
                        if not changes:
                            self._poll_commits(repos, now)
                except Exception:
                    self._log.exception("index watch loop failed")
                    self._stop.wait(0.5)
        except Exception:
            self._log.exception("index watcher stopped")

    def _note(self, repo_id: str, paths: Sequence[Path], now: float) -> None:
        held = self._pending.get(repo_id)
        if held is None:
            self._pending[repo_id] = _Pending(paths=list(paths), last_at=now)
            return
        held.paths.extend(paths)
        held.last_at = now

    def _flush_due(self, by_id: dict[str, EnrolledRepository], now: float) -> None:
        due: list[str] = []
        for repo_id, held in self._pending.items():
            repo = by_id.get(repo_id)
            if repo is None:
                due.append(repo_id)
                continue
            wait_s = max(repo.policy.indexing.debounce_ms, 0) / 1000.0
            if now - held.last_at >= wait_s:
                due.append(repo_id)
        for repo_id in due:
            held = self._pending.pop(repo_id)
            repo = by_id.get(repo_id)
            if repo is None:
                continue
            self.apply_changes(repo, held.paths)

    def _poll_commits(self, repos: Sequence[EnrolledRepository], now: float) -> None:
        for repo in repos:
            if repo.id.value in self._pending:
                continue
            interval_s = max(repo.policy.indexing.debounce_ms, _COMMIT_POLL_MIN_MS) / 1000.0
            last = self._commit_poll_at.get(repo.id.value)
            if last is not None and now - last < interval_s:
                continue
            self._commit_poll_at[repo.id.value] = now
            try:
                root = Path(repo.realpath).resolve()
                current = head_commit(root)
                indexed_commit, indexed_dirty = self._probe(repo.id.value).indexed_revision(
                    repo.id.value
                )
                current_dirty = list_dirty_paths(root)
                if current == indexed_commit and set(current_dirty) == set(indexed_dirty):
                    continue
                self._note(repo.id.value, (root / ".git" / "HEAD",), now)
            except Exception:
                self._log.exception("index watch commit poll failed")

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
            if not _repo_watch_enabled(record, self._probe(record.id.value)):
                continue
            watched.append(record)
        return tuple(watched)

    def _probe(self, repo_id: str) -> IndexingService:
        held = self._probes.get(repo_id)
        if held is not None:
            return held
        if self._meta_indexer is not None:
            self._probes[repo_id] = self._meta_indexer
            return self._meta_indexer
        created = self._indexer_factory()
        self._probes[repo_id] = created
        return created


def _repo_watch_enabled(repo: EnrolledRepository, indexer: IndexingService) -> bool:
    try:
        return indexer.watch_enabled(repo.id.value, policy=repo.policy)
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
