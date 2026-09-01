# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a user-typed command in an enrolled workspace. No push. No engine secrets."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, TypedDict

COMMAND_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 200_000
POLL_INTERVAL_SECONDS = 0.15
DRAIN_TIMEOUT_SECONDS = 2.0
_SECRET_ENV_SUFFIXES = ("_TOKEN", "_API_KEY", "_SECRET", "_PASSWORD")


class TerminalRun(TypedDict):
    command: str
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    output: str


@dataclass
class _ActiveRun:
    process: subprocess.Popen[str]
    cancelled: bool = False


_ACTIVE: dict[str, _ActiveRun] = {}
_ACTIVE_LOCK = Lock()


def terminal_run_key(repository_id: str) -> str:
    return f"terminal:{repository_id}"


def cancel_workspace_command(run_key: str) -> bool:
    with _ACTIVE_LOCK:
        active = _ACTIVE.get(run_key)
        if active is None:
            return False
        active.cancelled = True
        process = active.process
    _kill_process_tree(process)
    return True


def run_workspace_command(
    root: Path,
    command: str,
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    run_key: str | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> TerminalRun:
    stripped = command.strip()
    if stripped == "":
        raise ValueError("A command is required.")
    cwd = root.resolve()
    process = _spawn_shell(stripped, cwd=cwd)
    active = _ActiveRun(process=process)
    if run_key:
        with _ACTIVE_LOCK:
            previous = _ACTIVE.get(run_key)
            _ACTIVE[run_key] = active
        if previous is not None:
            _kill_process_tree(previous.process)
    try:
        return _wait_for_run(
            active,
            command=stripped,
            timeout_seconds=timeout_seconds,
            should_stop=should_stop,
            run_key=run_key,
        )
    finally:
        if run_key:
            with _ACTIVE_LOCK:
                if _ACTIVE.get(run_key) is active:
                    _ACTIVE.pop(run_key, None)


def _wait_for_run(
    active: _ActiveRun,
    *,
    command: str,
    timeout_seconds: float,
    should_stop: Callable[[], bool] | None,
    run_key: str | None,
) -> TerminalRun:
    process = active.process
    deadline = time.monotonic() + timeout_seconds
    while True:
        if should_stop is not None and should_stop():
            if run_key:
                cancel_workspace_command(run_key)
            else:
                active.cancelled = True
                _kill_process_tree(process)
        if active.cancelled:
            output = _drain(process)
            return {
                "command": command,
                "exit_code": process.returncode,
                "timed_out": False,
                "cancelled": True,
                "output": _clip_output(output),
            }
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            active.cancelled = False
            _kill_process_tree(process)
            output = _drain(process)
            return {
                "command": command,
                "exit_code": None,
                "timed_out": True,
                "cancelled": False,
                "output": _clip_output(output),
            }
        try:
            stdout, _stderr = process.communicate(timeout=min(POLL_INTERVAL_SECONDS, remaining))
            return {
                "command": command,
                "exit_code": process.returncode,
                "timed_out": False,
                "cancelled": False,
                "output": _clip_output(_as_text(stdout)),
            }
        except subprocess.TimeoutExpired:
            continue


def _spawn_shell(command: str, *, cwd: Path) -> subprocess.Popen[str]:
    shared: dict[str, object] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "env": _child_env(),
        **_windows_process_flags(),
    }
    if os.name == "nt":
        return subprocess.Popen(command, shell=True, **shared)  # noqa: S602
    return subprocess.Popen(["/bin/sh", "-c", command], start_new_session=True, **shared)  # noqa: S603


def _drain(process: subprocess.Popen[str]) -> str:
    try:
        stdout, _stderr = process.communicate(timeout=DRAIN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        stdout, _stderr = process.communicate(timeout=DRAIN_TIMEOUT_SECONDS)
    return _as_text(stdout)


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(  # noqa: S603
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
            creationflags=flags,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            return


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        upper = key.upper()
        if upper.startswith("KRONOS_") or upper.endswith(_SECRET_ENV_SUFFIXES):
            env.pop(key, None)
    return env


def _windows_process_flags() -> dict[str, int]:
    if os.name != "nt":
        return {}
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": no_window} if no_window else {}


def _as_text(chunk: str | bytes | None) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="replace")
    return chunk


def _clip_output(output: str) -> str:
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    return f"{output[:MAX_OUTPUT_CHARS]}\n[output truncated]\n"
