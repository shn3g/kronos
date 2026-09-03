# SPDX-License-Identifier: AGPL-3.0-or-later
"""Supervise in-process background workers: restart on death with backoff."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

StartFn = Callable[[], None]
StopFn = Callable[[], None]
AliveFn = Callable[[], bool]
DetailFn = Callable[[], str | None]


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    name: str
    running: bool
    alive: bool
    detail: str | None = None
    failures: int = 0
    restarts: int = 0


@dataclass
class _Component:
    name: str
    start: StartFn
    stop: StopFn
    is_alive: AliveFn
    detail: DetailFn | None = None
    running: bool = False
    failures: int = 0
    restarts: int = 0
    last_restart: float | None = None


class ComponentSupervisor:
    def __init__(
        self,
        *,
        max_restarts: int = 10,
        backoff_seconds: float = 1.0,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._max_restarts = max_restarts
        self._backoff_seconds = backoff_seconds
        self._now = now or time.monotonic
        self._lock = threading.RLock()
        self._components: dict[str, _Component] = {}

    def register(
        self,
        name: str,
        *,
        start: StartFn,
        stop: StopFn,
        is_alive: AliveFn,
        detail: DetailFn | None = None,
    ) -> None:
        with self._lock:
            self._components[name] = _Component(
                name=name,
                start=start,
                stop=stop,
                is_alive=is_alive,
                detail=detail,
            )

    def start(self, name: str) -> None:
        with self._lock:
            component = self._require(name)
            if component.running:
                return
            component.running = True
            component.start()

    def stop(self, name: str) -> None:
        with self._lock:
            component = self._require(name)
            if not component.running:
                return
            component.running = False
            component.stop()

    def restart(self, name: str) -> None:
        with self._lock:
            component = self._require(name)
            if component.running:
                component.stop()
            component.running = True
            component.start()
            component.restarts += 1
            component.last_restart = self._now()

    def status(self, name: str | None = None) -> list[ComponentStatus]:
        with self._lock:
            names = (name,) if name is not None else tuple(self._components)
            return [self._status_for(self._require(item)) for item in names]

    def start_all(self) -> None:
        with self._lock:
            for component in self._components.values():
                if component.running:
                    continue
                component.running = True
                component.start()

    def stop_all(self) -> None:
        with self._lock:
            for component in self._components.values():
                if not component.running:
                    continue
                component.running = False
                component.stop()

    def supervise_once(self) -> None:
        with self._lock:
            for component in self._components.values():
                if not component.running:
                    continue
                if component.is_alive():
                    continue
                component.failures += 1
                if component.restarts >= self._max_restarts:
                    continue
                now = self._now()
                if component.last_restart is not None:
                    backoff = min(
                        self._backoff_seconds * (2 ** min(component.failures - 1, 6)),
                        60.0,
                    )
                    if now - component.last_restart < backoff:
                        continue
                try:
                    component.stop()
                except Exception:
                    # A dead worker may fail to stop cleanly; still attempt the restart.
                    pass
                try:
                    component.start()
                except Exception:
                    # Count failed starts toward the restart budget so a broken
                    # starter cannot spin forever without tripping max_restarts.
                    pass
                component.restarts += 1
                component.last_restart = now

    def _require(self, name: str) -> _Component:
        component = self._components.get(name)
        if component is None:
            raise KeyError(name)
        return component

    def _status_for(self, component: _Component) -> ComponentStatus:
        detail = component.detail() if component.detail is not None else None
        alive = component.is_alive() if component.running else False
        return ComponentStatus(
            name=component.name,
            running=component.running,
            alive=alive,
            detail=detail,
            failures=component.failures,
            restarts=component.restarts,
        )
