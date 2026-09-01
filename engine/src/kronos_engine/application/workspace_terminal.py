# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a user-typed command in an enrolled workspace. No push. No engine secrets."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TypedDict

COMMAND_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 200_000
_SECRET_ENV_SUFFIXES = ("_TOKEN", "_API_KEY", "_SECRET", "_PASSWORD")


class TerminalRun(TypedDict):
    command: str
    exit_code: int | None
    timed_out: bool
    output: str


def run_workspace_command(
    root: Path,
    command: str,
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
) -> TerminalRun:
    stripped = command.strip()
    if stripped == "":
        raise ValueError("A command is required.")
    cwd = root.resolve()
    try:
        completed = _invoke_shell(stripped, cwd=cwd, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        return {
            "command": stripped,
            "exit_code": None,
            "timed_out": True,
            "output": _clip_output(_combined_output(error.stdout, error.stderr)),
        }
    return {
        "command": stripped,
        "exit_code": completed.returncode,
        "timed_out": False,
        "output": _clip_output(_combined_output(completed.stdout, completed.stderr)),
    }


def _invoke_shell(
    command: str, *, cwd: Path, timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    shared = {
        "cwd": cwd,
        "check": False,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout_seconds,
        "env": _child_env(),
        **_windows_process_flags(),
    }
    if os.name == "nt":
        return subprocess.run(command, shell=True, **shared)  # noqa: S602
    return subprocess.run(["/bin/sh", "-c", command], **shared)  # noqa: S603


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


def _combined_output(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    return f"{_as_text(stdout)}{_as_text(stderr)}"


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
