# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from kronos_engine import __version__ as ENGINE_VERSION

ENGINE_ROOT = Path(__file__).resolve().parents[2]
SRC = ENGINE_ROOT / "src"


def _engine_env(tmp_path: Path, token: str) -> dict[str, str]:
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
            "KRONOS_BIND_PORT": "0",
        }
    )
    return env


def _start(env: dict[str, str], *, command: list[str] | None = None) -> subprocess.Popen[str]:
    launch = command or [sys.executable, "-m", "kronos_engine"]
    return subprocess.Popen(
        launch,
        cwd=str(ENGINE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def _wait_ready_line(proc: subprocess.Popen[str], timeout: float = 15.0) -> str:
    deadline = time.monotonic() + timeout
    assert proc.stdout is not None
    lines: list[str] = []
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            rest = proc.stdout.read()
            raise RuntimeError(f"engine exited {proc.returncode}: {''.join(lines)}{rest}")
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        lines.append(line)
        if line.startswith("KRONOS_READY "):
            return line.strip().split(" ", 1)[1]
        time.sleep(0.01)
    raise TimeoutError(f"KRONOS_READY not printed: {''.join(lines)}")


def _stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.kill()
        proc.communicate(timeout=5)


def probe_engine_state(
    base_url: str,
    token: str,
    *,
    client_version: str = ENGINE_VERSION,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Kronos-Client-Version": client_version,
    }
    try:
        health = httpx.get(f"{base_url}/health", headers=headers, timeout=2.0)
        if health.status_code != 200 or health.json().get("status") != "ok":
            return {"status": "unavailable"}
        version = httpx.get(f"{base_url}/version", headers=headers, timeout=2.0)
        if version.status_code != 200:
            return {"status": "unavailable"}
        body = version.json()
        if body.get("compatible") is not True:
            return {
                "status": "incompatible",
                "clientVersion": client_version,
                "engineVersion": str(body.get("engine_version") or "unknown"),
            }
        engine_version = body.get("engine_version")
        if not isinstance(engine_version, str) or engine_version == "":
            return {"status": "unavailable"}
        return {"status": "ready", "version": engine_version}
    except httpx.HTTPError:
        return {"status": "unavailable"}


@pytest.mark.integration
def test_desktop_probe_path_is_ready_and_can_read_events(tmp_path: Path) -> None:
    token = "desktop-probe-token"
    proc = _start(_engine_env(tmp_path, token))
    try:
        base_url = _wait_ready_line(proc).rstrip("/")
        assert base_url.startswith("http://127.0.0.1:")
        state = probe_engine_state(base_url, token)
        assert state == {"status": "ready", "version": ENGINE_VERSION}

        events = httpx.get(
            f"{base_url}/events",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2.0,
        )
        assert events.status_code == 200
        payload = events.json()
        assert payload["events"] == []
        assert payload["head_seq"] == 0
    finally:
        _stop(proc)


@pytest.mark.integration
def test_desktop_probe_bundled_binary_when_env_set(tmp_path: Path) -> None:
    raw_bin = os.environ.get("KRONOS_ENGINE_BIN", "").strip()
    if not raw_bin:
        pytest.skip("KRONOS_ENGINE_BIN is not set")
    bundled = Path(raw_bin)
    if not bundled.is_file():
        pytest.skip(f"KRONOS_ENGINE_BIN does not point at a file: {bundled}")

    token = "desktop-probe-bundled-token"
    proc = _start(_engine_env(tmp_path, token), command=[str(bundled)])
    try:
        base_url = _wait_ready_line(proc, timeout=20.0).rstrip("/")
        assert base_url.startswith("http://127.0.0.1:")
        state = probe_engine_state(base_url, token)
        assert state == {"status": "ready", "version": ENGINE_VERSION}
    finally:
        _stop(proc)
