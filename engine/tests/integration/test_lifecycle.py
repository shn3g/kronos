# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from kronos_engine.application.recorder import Recorder
from kronos_engine.domain.entities import EventId
from kronos_engine.state.database import connect
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.outbox import SqliteOutbox


def make_recorder(conn: sqlite3.Connection) -> Recorder:
    return Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn))


ENGINE_ROOT = Path(__file__).resolve().parents[2]
SRC = ENGINE_ROOT / "src"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _engine_env(tmp_path: Path, port: int, token: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SRC),
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
            "KRONOS_AUTH_TOKEN": token,
            "KRONOS_BIND_HOST": "127.0.0.1",
            "KRONOS_BIND_PORT": str(port),
        }
    )
    return env


def _start(env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "kronos_engine"],
        cwd=str(ENGINE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_ready(
    base_url: str,
    token: str,
    proc: subprocess.Popen[str],
    timeout: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout
    headers = {"Authorization": f"Bearer {token}"}
    last_error = "not started"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"engine exited {proc.returncode}: {output}")
        try:
            response = httpx.get(f"{base_url}/health", headers=headers, timeout=0.2)
            if response.status_code == 200:
                return
            last_error = f"status {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.05)
    output = ""
    if proc.stdout:
        # Best-effort snapshot; process is still running.
        pass
    raise TimeoutError(f"engine was not healthy: {last_error} {output}")


def _stop(proc: subprocess.Popen[str]) -> str:
    output = ""
    if proc.poll() is None:
        proc.kill()
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=5)
    elif proc.stdout:
        output = proc.stdout.read()
    return output


@pytest.mark.integration
def test_kill_and_restart_preserves_state_without_duplicate_outbox(tmp_path: Path) -> None:
    token = "lifecycle-token"
    port = _free_port()
    env = _engine_env(tmp_path, port, token)
    base_url = f"http://127.0.0.1:{port}"
    db_path = tmp_path / "data" / "kronos.sqlite3"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Kronos-Client-Version": "0.1.0",
    }

    first = _start(env)
    try:
        _wait_ready(base_url, token, first)
        conn = connect(db_path)
        make_recorder(conn).record(
            EventId("evt-keep"),
            "GoalRecorded",
            {"goal_id": "g1"},
            {"action": "notify"},
        )
        conn.close()
        events = httpx.get(f"{base_url}/events", headers=headers, timeout=2.0)
        assert events.status_code == 200
        assert len(events.json()["events"]) == 1
        version = httpx.get(f"{base_url}/version", headers=headers, timeout=2.0)
        assert version.json()["compatible"] is True
    finally:
        _stop(first)

    restarted = _start(env)
    try:
        _wait_ready(base_url, token, restarted)
        events = httpx.get(f"{base_url}/events", headers=headers, timeout=2.0)
        assert events.status_code == 200
        payload = events.json()["events"]
        assert len(payload) == 1
        assert payload[0]["id"] == "evt-keep"
        conn = connect(db_path)
        try:
            undispatched = SqliteOutbox(conn).undispatched()
            assert len(undispatched) == 1
            assert undispatched[0].payload == {"action": "notify"}
        finally:
            conn.close()
    finally:
        _stop(restarted)
