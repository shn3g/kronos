# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a user-typed command in an enrolled workspace. No push. No engine secrets."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import TypedDict

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
    running: bool
    output: str


@dataclass
class _ActiveRun:
    command: str
    chunks: list[str]
    lock: Lock
    reader: Thread
    process: subprocess.Popen[str] | None = None
    cancelled: bool = False
    timed_out: bool = False

    def poll(self) -> int | None:
        if self.process is not None:
            return self.process.poll()
        return 0

    def kill(self) -> None:
        if self.process is not None:
            _kill_process_tree(self.process)


_ACTIVE: dict[str, _ActiveRun] = {}
_ACTIVE_LOCK = Lock()


def terminal_run_key(repository_id: str) -> str:
    return f"terminal:{repository_id}"


def peek_workspace_command(run_key: str) -> TerminalRun | None:
    with _ACTIVE_LOCK:
        active = _ACTIVE.get(run_key)
        if active is None:
            return None
        return _snapshot(active, running=active.poll() is None)


def cancel_workspace_command(run_key: str) -> bool:
    with _ACTIVE_LOCK:
        active = _ACTIVE.pop(run_key, None)
        if active is None:
            return False
        active.cancelled = True
    active.kill()
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
    chunks: list[str] = []
    lock = Lock()
    reader = Thread(target=_pump_stdout, args=(process, chunks, lock), daemon=True)
    active = _ActiveRun(
        command=stripped,
        chunks=chunks,
        lock=lock,
        reader=reader,
        process=process,
    )
    reader.start()
    if run_key:
        with _ACTIVE_LOCK:
            previous = _ACTIVE.get(run_key)
            _ACTIVE[run_key] = active
        if previous is not None:
            previous.kill()
    try:
        return _wait_for_run(
            active,
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
    timeout_seconds: float,
    should_stop: Callable[[], bool] | None,
    run_key: str | None,
) -> TerminalRun:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if should_stop is not None and should_stop():
            if run_key:
                cancel_workspace_command(run_key)
            else:
                active.cancelled = True
                active.kill()
        if active.cancelled:
            _join_reader(active)
            return _snapshot(active, running=False)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            active.timed_out = True
            active.kill()
            _join_reader(active)
            snap = _snapshot(active, running=False)
            snap["exit_code"] = None
            return snap
        if active.poll() is not None:
            _join_reader(active)
            return _snapshot(active, running=False)
        time.sleep(min(POLL_INTERVAL_SECONDS, remaining))


def _pump_stdout(process: subprocess.Popen[str], chunks: list[str], lock: Lock) -> None:
    stream = process.stdout
    if stream is None:
        return
    while True:
        piece = stream.readline()
        if piece == "":
            break
        _append_output(chunks, lock, piece)


def _append_output(chunks: list[str], lock: Lock, piece: str) -> None:
    with lock:
        joined = "".join(chunks)
        if len(joined) >= MAX_OUTPUT_CHARS:
            return
        chunks.append(piece)
        joined = "".join(chunks)
        if len(joined) > MAX_OUTPUT_CHARS:
            chunks.clear()
            chunks.append(_clip_output(joined))


def _join_reader(active: _ActiveRun) -> None:
    active.reader.join(timeout=DRAIN_TIMEOUT_SECONDS)


def _snapshot(active: _ActiveRun, *, running: bool) -> TerminalRun:
    with active.lock:
        output = "".join(active.chunks)
    return {
        "command": active.command,
        "exit_code": None if active.timed_out else active.poll(),
        "timed_out": active.timed_out,
        "cancelled": active.cancelled,
        "running": running,
        "output": _clip_output(output),
    }


def _spawn_shell(command: str, *, cwd: Path) -> subprocess.Popen[str]:
    if os.name == "nt":
        return subprocess.Popen(  # noqa: S602
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_child_env(),
            creationflags=_no_window_flag(),
        )
    return subprocess.Popen(  # noqa: S603
        ["/bin/sh", "-c", command],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=_child_env(),
        start_new_session=True,
    )


def _kill_process_tree(process: subprocess.Popen[str] | subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(  # noqa: S603
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
            creationflags=_no_window_flag(),
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
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TERM", "xterm-256color")
    env["COLORTERM"] = "truecolor"
    for key in list(env):
        upper = key.upper()
        if upper.startswith("KRONOS_") or upper.endswith(_SECRET_ENV_SUFFIXES):
            env.pop(key, None)
    return env


def _no_window_flag() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _clip_output(output: str) -> str:
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    return f"{output[:MAX_OUTPUT_CHARS]}\n[output truncated]\n"
