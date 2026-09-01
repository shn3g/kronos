# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a user-typed command in an enrolled workspace. No push. No engine secrets."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Protocol, TypedDict

COMMAND_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 200_000
POLL_INTERVAL_SECONDS = 0.15
DRAIN_TIMEOUT_SECONDS = 2.0
DEFAULT_SHELL_ROWS = 24
DEFAULT_SHELL_COLS = 80
MIN_SHELL_COLS = 8
MAX_SHELL_COLS = 400
MIN_SHELL_ROWS = 4
MAX_SHELL_ROWS = 200
_SECRET_ENV_SUFFIXES = ("_TOKEN", "_API_KEY", "_SECRET", "_PASSWORD")


class TerminalRun(TypedDict):
    command: str
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    running: bool
    output: str


class _PtySession(Protocol):
    def poll(self) -> int | None: ...
    def write(self, data: str) -> bool: ...
    def read(self) -> str: ...
    def kill(self) -> None: ...
    def resize(self, cols: int, rows: int) -> bool: ...


@dataclass
class _ActiveRun:
    command: str
    chunks: list[str]
    lock: Lock
    reader: Thread
    process: subprocess.Popen[str] | None = None
    session: _PtySession | None = None
    cancelled: bool = False
    timed_out: bool = False

    def poll(self) -> int | None:
        if self.session is not None:
            return self.session.poll()
        if self.process is not None:
            return self.process.poll()
        return 0

    def kill(self) -> None:
        if self.session is not None:
            self.session.kill()
            return
        if self.process is not None:
            _kill_process_tree(self.process)

    def write(self, data: str) -> bool:
        if self.session is not None:
            return self.session.write(data)
        stdin = None if self.process is None else self.process.stdin
        if stdin is None:
            return False
        try:
            stdin.write(data)
            stdin.flush()
        except OSError:
            return False
        return True


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


def start_workspace_shell(root: Path, *, run_key: str) -> TerminalRun:
    cwd = root.resolve()
    with _ACTIVE_LOCK:
        existing = _ACTIVE.get(run_key)
        if existing is not None and existing.poll() is None:
            return _snapshot(existing, running=True)
        previous = _ACTIVE.pop(run_key, None)
    if previous is not None:
        previous.kill()
        _join_reader(previous)
    session = _open_pty_session(cwd)
    chunks: list[str] = []
    lock = Lock()
    reader = Thread(target=_pump_session, args=(session, chunks, lock), daemon=True)
    active = _ActiveRun(
        command="shell",
        chunks=chunks,
        lock=lock,
        reader=reader,
        session=session,
    )
    reader.start()
    with _ACTIVE_LOCK:
        _ACTIVE[run_key] = active
    return _snapshot(active, running=active.poll() is None)


def write_workspace_shell(run_key: str, data: str) -> bool:
    if data == "":
        return False
    encoded = _encode_shell_input(data)
    with _ACTIVE_LOCK:
        active = _ACTIVE.get(run_key)
        if active is None or active.poll() is not None:
            return False
        stripped = data.strip()
        if stripped != "":
            active.command = stripped.splitlines()[0][:200]
    return active.write(encoded)


def resize_workspace_shell(run_key: str, *, cols: int, rows: int) -> bool:
    if cols < MIN_SHELL_COLS or cols > MAX_SHELL_COLS:
        return False
    if rows < MIN_SHELL_ROWS or rows > MAX_SHELL_ROWS:
        return False
    with _ACTIVE_LOCK:
        active = _ACTIVE.get(run_key)
        if active is None or active.poll() is not None or active.session is None:
            return False
        session = active.session
    return session.resize(cols, rows)


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


def _pump_session(session: _PtySession, chunks: list[str], lock: Lock) -> None:
    while True:
        piece = session.read()
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


def _open_pty_session(cwd: Path) -> _PtySession:
    if os.name == "nt":
        return _WinPtySession.open(cwd)
    return _PosixPtySession.open(cwd)


def _encode_shell_input(data: str) -> str:
    if os.name != "nt":
        return data
    return data.replace("\r\n", "\n").replace("\n", "\r")


class _WinPtySession:
    def __init__(self, proc: object) -> None:
        self._proc = proc

    @classmethod
    def open(cls, cwd: Path) -> _WinPtySession:
        from winpty import PtyProcess

        proc = PtyProcess.spawn(
            "cmd.exe /K",
            cwd=str(cwd),
            env=_child_env(),
            dimensions=(DEFAULT_SHELL_ROWS, DEFAULT_SHELL_COLS),
        )
        return cls(proc)

    def poll(self) -> int | None:
        proc = self._proc
        if bool(getattr(proc, "isalive")()):
            return None
        status = getattr(proc, "exitstatus", 0)
        return 0 if status is None else int(status)

    def write(self, data: str) -> bool:
        try:
            getattr(self._proc, "write")(data)
        except OSError:
            return False
        return True

    def read(self) -> str:
        proc = self._proc
        try:
            chunk = getattr(proc, "read")(4096)
        except (OSError, EOFError):
            return ""
        if chunk in (None, "", b""):
            return ""
        if isinstance(chunk, bytes):
            return chunk.decode("utf-8", errors="replace")
        return str(chunk)

    def kill(self) -> None:
        proc = self._proc
        try:
            getattr(proc, "terminate")(force=True)
        except (OSError, TypeError):
            try:
                getattr(proc, "terminate")()
            except OSError:
                return
        try:
            getattr(proc, "close")()
        except (OSError, TypeError):
            return

    def resize(self, cols: int, rows: int) -> bool:
        try:
            getattr(self._proc, "setwinsize")(rows, cols)
        except OSError:
            return False
        return True


class _PosixPtySession:
    def __init__(self, process: subprocess.Popen[bytes], master_fd: int) -> None:
        self._process = process
        self._master_fd = master_fd

    @classmethod
    def open(cls, cwd: Path) -> _PosixPtySession:
        import pty

        master_fd, slave_fd = pty.openpty()
        _set_posix_winsize(slave_fd, DEFAULT_SHELL_COLS, DEFAULT_SHELL_ROWS)
        process = subprocess.Popen(  # noqa: S603
            ["/bin/sh"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=_child_env(),
            start_new_session=True,
        )
        os.close(slave_fd)
        return cls(process, master_fd)

    def poll(self) -> int | None:
        return self._process.poll()

    def write(self, data: str) -> bool:
        try:
            os.write(self._master_fd, data.encode("utf-8", errors="replace"))
        except OSError:
            return False
        return True

    def read(self) -> str:
        try:
            piece = os.read(self._master_fd, 4096)
        except OSError:
            return ""
        if piece == b"":
            return ""
        return piece.decode("utf-8", errors="replace")

    def kill(self) -> None:
        _kill_process_tree(self._process)
        try:
            os.close(self._master_fd)
        except OSError:
            return

    def resize(self, cols: int, rows: int) -> bool:
        if not _set_posix_winsize(self._master_fd, cols, rows):
            return False
        try:
            os.kill(self._process.pid, signal.SIGWINCH)
        except (ProcessLookupError, PermissionError, OSError):
            return False
        return True


def _set_posix_winsize(fd: int, cols: int, rows: int) -> bool:
    import fcntl
    import struct
    import termios

    packed = struct.pack("HHHH", rows, cols, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)
    except OSError:
        return False
    return True


def _spawn_shell(command: str, *, cwd: Path) -> subprocess.Popen[str]:
    shared: dict[str, object] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "env": _child_env(),
        **_windows_process_flags(),
    }
    if os.name == "nt":
        return subprocess.Popen(command, shell=True, **shared)  # noqa: S602
    return subprocess.Popen(["/bin/sh", "-c", command], start_new_session=True, **shared)  # noqa: S603


def _kill_process_tree(process: subprocess.Popen[str] | subprocess.Popen[bytes]) -> None:
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
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TERM", "xterm-256color")
    env["COLORTERM"] = "truecolor"
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


def _clip_output(output: str) -> str:
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    return f"{output[:MAX_OUTPUT_CHARS]}\n[output truncated]\n"
