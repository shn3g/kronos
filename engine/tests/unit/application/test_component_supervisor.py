# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ComponentSupervisor."""

from __future__ import annotations

from kronos_engine.application.component_supervisor import ComponentSupervisor


class _Probe:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0
        self.alive = False

    def start(self) -> None:
        self.starts += 1
        self.alive = True

    def stop(self) -> None:
        self.stops += 1
        self.alive = False

    def is_alive(self) -> bool:
        return self.alive


def test_register_start_reports_alive() -> None:
    probe = _Probe()
    supervisor = ComponentSupervisor(backoff_seconds=0.0)
    supervisor.register("worker", start=probe.start, stop=probe.stop, is_alive=probe.is_alive)
    supervisor.start("worker")
    status = supervisor.status("worker")[0]
    assert status.running is True
    assert status.alive is True
    assert probe.starts == 1


def test_stop_marks_not_running() -> None:
    probe = _Probe()
    supervisor = ComponentSupervisor(backoff_seconds=0.0)
    supervisor.register("worker", start=probe.start, stop=probe.stop, is_alive=probe.is_alive)
    supervisor.start("worker")
    supervisor.stop("worker")
    status = supervisor.status("worker")[0]
    assert status.running is False
    assert status.alive is False
    assert probe.stops == 1


def test_supervise_once_restarts_dead_component_that_should_be_running() -> None:
    probe = _Probe()
    supervisor = ComponentSupervisor(backoff_seconds=0.0)
    supervisor.register("worker", start=probe.start, stop=probe.stop, is_alive=probe.is_alive)
    supervisor.start("worker")
    probe.alive = False
    supervisor.supervise_once()
    assert probe.starts == 2
    status = supervisor.status("worker")[0]
    assert status.restarts == 1
    assert status.failures == 1
    assert status.alive is True


def test_supervise_once_counts_failed_starts_toward_restart_budget() -> None:
    class _Broken:
        def __init__(self) -> None:
            self.starts = 0

        def start(self) -> None:
            self.starts += 1
            raise RuntimeError("cannot start")

        def stop(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

    broken = _Broken()
    supervisor = ComponentSupervisor(max_restarts=2, backoff_seconds=0.0)
    supervisor.register(
        "worker",
        start=broken.start,
        stop=broken.stop,
        is_alive=broken.is_alive,
    )
    # Mark running without a successful start so supervise sees a dead worker.
    try:
        supervisor.start("worker")
    except RuntimeError:
        pass
    assert broken.starts == 1

    supervisor.supervise_once()
    supervisor.supervise_once()
    assert broken.starts == 3
    assert supervisor.status("worker")[0].restarts == 2

    supervisor.supervise_once()
    assert broken.starts == 3
    assert supervisor.status("worker")[0].restarts == 2


def test_stop_all_stops_everything() -> None:
    first = _Probe()
    second = _Probe()
    supervisor = ComponentSupervisor(backoff_seconds=0.0)
    supervisor.register("a", start=first.start, stop=first.stop, is_alive=first.is_alive)
    supervisor.register("b", start=second.start, stop=second.stop, is_alive=second.is_alive)
    supervisor.start_all()
    supervisor.stop_all()
    assert first.alive is False and second.alive is False
    assert all(item.running is False for item in supervisor.status())
