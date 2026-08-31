# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two fixture git repos enrolled, restarted, isolated, with no runtime files in-tree."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from tests.support.git_fixtures import init_git_repo

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
    raise TimeoutError(f"engine was not healthy: {last_error}")


def _stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


def _assert_clean_tree(root: Path) -> None:
    names = {path.name for path in root.iterdir()}
    assert ".kronos" not in names
    assert ".worktrees" not in names
    assert "kronos.sqlite3" not in names
    assert list(root.rglob("TICKET.md")) == []
    assert list(root.rglob("kronos.sqlite3")) == []


@pytest.mark.integration
def test_two_fixture_repos_enrol_restart_and_stay_isolated(tmp_path: Path) -> None:
    token = "enrol-token"
    port = _free_port()
    env = _engine_env(tmp_path, port, token)
    base_url = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {token}", "X-Kronos-Client-Version": "0.1.0"}

    python_root = init_git_repo(
        tmp_path / "fixtures" / "python-app",
        origin="https://github.com/acme/python-app.git",
        files={
            "README.md": "python-app\n",
            "pyproject.toml": (
                "[project]\nname='python-app'\n[tool.pytest.ini_options]\ntestpaths=['tests']\n"
            ),
        },
    )
    node_root = init_git_repo(
        tmp_path / "fixtures" / "node-app",
        origin="https://github.com/acme/node-app.git",
        files={
            "README.md": "node-app\n",
            "package.json": '{"name":"node-app","scripts":{"test":"vitest","lint":"eslint ."}}',
            "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
        },
    )

    first = _start(env)
    try:
        _wait_ready(base_url, token, first)
        alpha = httpx.post(
            f"{base_url}/repositories",
            headers=headers,
            json={"path": str(python_root)},
            timeout=5.0,
        )
        beta = httpx.post(
            f"{base_url}/repositories",
            headers=headers,
            json={"path": str(node_root), "policy": {"autonomy": {"freeze": False}}},
            timeout=5.0,
        )
        assert alpha.status_code == 200, alpha.text
        assert beta.status_code == 200, beta.text
        alpha_id = alpha.json()["repository"]["id"]
        beta_id = beta.json()["repository"]["id"]
        listed = httpx.get(f"{base_url}/repositories", headers=headers, timeout=5.0)
        assert {item["id"] for item in listed.json()["repositories"]} == {alpha_id, beta_id}
        _assert_clean_tree(python_root)
        _assert_clean_tree(node_root)
    finally:
        _stop(first)

    restarted = _start(env)
    try:
        _wait_ready(base_url, token, restarted)
        listed = httpx.get(f"{base_url}/repositories", headers=headers, timeout=5.0)
        assert listed.status_code == 200
        ids = {item["id"] for item in listed.json()["repositories"]}
        assert len(ids) == 2
        alpha_id, beta_id = tuple(ids)
        alpha_get = httpx.get(f"{base_url}/repositories/{alpha_id}", headers=headers, timeout=5.0)
        beta_get = httpx.get(f"{base_url}/repositories/{beta_id}", headers=headers, timeout=5.0)
        freezes = {
            alpha_get.json()["policy"]["autonomy"]["freeze"],
            beta_get.json()["policy"]["autonomy"]["freeze"],
        }
        assert freezes == {True, False}
        assert alpha_get.json()["repository"]["id"] != beta_get.json()["repository"]["id"]
        missing = httpx.get(f"{base_url}/repositories/repo_other", headers=headers, timeout=5.0)
        assert missing.status_code == 404
        runtime = alpha_get.json()["runtime"]
        assert str(python_root.resolve()) not in runtime["state_dir"]
        assert str(node_root.resolve()) not in runtime["state_dir"]
        _assert_clean_tree(python_root)
        _assert_clean_tree(node_root)
    finally:
        _stop(restarted)
