# SPDX-License-Identifier: AGPL-3.0-or-later

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from kronos_engine.domain.entities import Lease
from kronos_engine.domain.results import LockHeldError, StaleFenceError
from kronos_engine.state.database import connect
from kronos_engine.state.leases import SqliteLeases

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def test_acquire_issues_fence_token(tmp_path: Path) -> None:
    leases = SqliteLeases(connect(tmp_path / "kronos.sqlite3"))
    lease = leases.acquire("repo-1:src", "holder-a", timedelta(seconds=60), now=NOW)
    assert lease.fence_token == 1
    assert lease.holder_id == "holder-a"
    assert lease.expires_at == NOW + timedelta(seconds=60)


def test_expired_lease_can_be_stolen(tmp_path: Path) -> None:
    leases = SqliteLeases(connect(tmp_path / "kronos.sqlite3"))
    first = leases.acquire("repo-1:src", "holder-a", timedelta(seconds=30), now=NOW)
    stolen = leases.acquire(
        "repo-1:src",
        "holder-b",
        timedelta(seconds=30),
        now=NOW + timedelta(seconds=31),
    )
    assert stolen.holder_id == "holder-b"
    assert stolen.fence_token == first.fence_token + 1
    with pytest.raises(StaleFenceError):
        leases.assert_fence("repo-1:src", first.fence_token, now=NOW + timedelta(seconds=31))
    leases.assert_fence("repo-1:src", stolen.fence_token, now=NOW + timedelta(seconds=31))


def test_live_foreign_lock_is_refused(tmp_path: Path) -> None:
    leases = SqliteLeases(connect(tmp_path / "kronos.sqlite3"))
    leases.acquire("repo-1:src", "holder-a", timedelta(seconds=60), now=NOW)
    with pytest.raises(LockHeldError):
        leases.acquire(
            "repo-1:src",
            "holder-b",
            timedelta(seconds=60),
            now=NOW + timedelta(seconds=5),
        )


def test_same_holder_renews_without_changing_fence(tmp_path: Path) -> None:
    leases = SqliteLeases(connect(tmp_path / "kronos.sqlite3"))
    first = leases.acquire("repo-1:src", "holder-a", timedelta(seconds=60), now=NOW)
    renewed = leases.acquire(
        "repo-1:src",
        "holder-a",
        timedelta(seconds=60),
        now=NOW + timedelta(seconds=10),
    )
    assert renewed.fence_token == first.fence_token
    assert renewed.expires_at == NOW + timedelta(seconds=70)


@given(st.integers(min_value=1, max_value=40))
@settings(max_examples=20, deadline=10_000)
def test_steal_count_matches_fence_token(ttl_seconds: int) -> None:
    with TemporaryDirectory() as raw:
        conn = connect(Path(raw) / "kronos.sqlite3")
        try:
            leases = SqliteLeases(conn)
            now = NOW
            lease = leases.acquire("r", "h0", timedelta(seconds=ttl_seconds), now=now)
            for i in range(3):
                now = lease.expires_at + timedelta(seconds=1)
                lease = leases.acquire("r", f"h{i + 1}", timedelta(seconds=ttl_seconds), now=now)
            assert lease.fence_token == 4
            assert lease.holder_id == "h3"
        finally:
            conn.close()


def test_concurrent_steal_of_expired_lease_has_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "kronos.sqlite3"
    setup = connect(path)
    try:
        SqliteLeases(setup).acquire("r", "holder-a", timedelta(seconds=30), now=NOW)
    finally:
        setup.close()

    steal_now = NOW + timedelta(seconds=31)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    guard = threading.Lock()

    def take(holder: str) -> None:
        conn = connect(path)
        try:
            barrier.wait(timeout=5)
            try:
                lease = SqliteLeases(conn).acquire(
                    "r", holder, timedelta(seconds=30), now=steal_now
                )
                with guard:
                    outcomes.append(lease)
            except Exception as exc:
                with guard:
                    outcomes.append(exc)
        finally:
            conn.close()

    threads = [
        threading.Thread(target=take, args=("holder-b",)),
        threading.Thread(target=take, args=("holder-c",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    wins = [item for item in outcomes if isinstance(item, Lease)]
    losses = [item for item in outcomes if isinstance(item, LockHeldError)]
    assert len(outcomes) == 2
    assert len(wins) == 1
    assert len(losses) == 1
    assert wins[0].fence_token == 2
    assert wins[0].holder_id in {"holder-b", "holder-c"}


def test_concurrent_first_acquire_has_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "kronos.sqlite3"
    connect(path).close()

    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    guard = threading.Lock()

    def take(holder: str) -> None:
        conn = connect(path)
        try:
            barrier.wait(timeout=5)
            try:
                lease = SqliteLeases(conn).acquire(
                    "fresh", holder, timedelta(seconds=30), now=NOW
                )
                with guard:
                    outcomes.append(lease)
            except Exception as exc:
                with guard:
                    outcomes.append(exc)
        finally:
            conn.close()

    threads = [
        threading.Thread(target=take, args=("holder-a",)),
        threading.Thread(target=take, args=("holder-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    wins = [item for item in outcomes if isinstance(item, Lease)]
    losses = [item for item in outcomes if isinstance(item, LockHeldError)]
    assert len(outcomes) == 2
    assert len(wins) == 1
    assert len(losses) == 1
    assert wins[0].fence_token == 1
    unexpected = [
        item
        for item in outcomes
        if isinstance(item, Exception) and not isinstance(item, LockHeldError)
    ]
    assert unexpected == []
