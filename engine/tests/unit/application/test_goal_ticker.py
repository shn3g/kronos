# SPDX-License-Identifier: AGPL-3.0-or-later
"""Background goal ticker advances the engine without the desktop Goals page."""

from __future__ import annotations

import threading

from kronos_engine.application.goal_ticker import advance_goal_engine, run_goal_ticker


class _FakeEngine:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.calls = 0
        self.fail_after = fail_after

    def tick(self) -> str:
        self.calls += 1
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise RuntimeError("tick exploded")
        return "ok"


def test_advance_goal_engine_invokes_tick() -> None:
    engine = _FakeEngine()
    advance_goal_engine(engine.tick)
    assert engine.calls == 1


def test_advance_goal_engine_is_fail_open() -> None:
    engine = _FakeEngine(fail_after=1)
    advance_goal_engine(engine.tick)
    assert engine.calls == 1


def test_run_goal_ticker_invokes_tick_without_desktop() -> None:
    engine = _FakeEngine()
    stop = threading.Event()

    def tick() -> str:
        result = engine.tick()
        if engine.calls >= 2:
            stop.set()
        return result

    run_goal_ticker(tick, stop, interval=0.01)
    assert engine.calls >= 2
