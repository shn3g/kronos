# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-open background ticks so planned goals advance without the Goals page."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

GOAL_TICK_INTERVAL_SECONDS = 1.5


def advance_goal_engine(tick: Callable[[], object]) -> None:
    try:
        tick()
    except Exception:
        logging.getLogger("kronos.engine").exception("background goal tick failed")


def run_goal_ticker(
    tick: Callable[[], object],
    stop: threading.Event,
    *,
    interval: float = GOAL_TICK_INTERVAL_SECONDS,
) -> None:
    while not stop.is_set():
        advance_goal_engine(tick)
        if stop.wait(interval):
            break
