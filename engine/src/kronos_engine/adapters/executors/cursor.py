# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional Cursor CLI executor behind the same fixture contract."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.models import assert_finite_attempts
from kronos_engine.ports.executor import ExecutorRequest, ExecutorResult, UsageMetadata
from kronos_engine.ports.sandbox import Sandbox

WhichFn = Callable[[str], str | None]
InvokeFn = Callable[[list[str], dict[str, str], Path, float], "CliResult"]


@dataclass(frozen=True, slots=True)
class CursorCli:
    path: str
    name: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def detect_cursor_cli(which: WhichFn | None = None) -> CursorCli | None:
    lookup = which or shutil.which
    for name in ("cursor-agent", "agent", "cursor"):
        path = lookup(name)
        if path:
            return CursorCli(path=path, name=name)
    return None


class CursorExecutor:
    def __init__(self, *, which: WhichFn | None = None, invoke: InvokeFn | None = None) -> None:
        self._which = which or shutil.which
        self._invoke = invoke or _subprocess_invoke

    def detect(self) -> CursorCli | None:
        return detect_cursor_cli(self._which)

    def run(self, request: ExecutorRequest, sandbox: Sandbox) -> ExecutorResult:
        if request.capabilities.autonomous_merge:
            sandbox.authorize_autonomous_merge()
        assert_finite_attempts(request.limits.max_attempts)
        sandbox.resolve(request.context.expected_artifact)
        env = sandbox.worker_environment(request.worker_env)
        detected = self.detect()
        if detected is None:
            return ExecutorResult(
                status="failed",
                artifacts=(),
                usage=_usage(0),
                error="cursor CLI was not detected",
            )
        argv = [
            detected.path,
            "--workspace",
            str(request.worktree),
            "--artifact",
            request.context.expected_artifact,
        ]
        result = self._invoke(argv, env, request.worktree, request.limits.timeout_seconds)
        if result.returncode != 0:
            return ExecutorResult(
                status="failed",
                artifacts=(),
                usage=_usage(1),
                error=result.stderr or "cursor CLI failed",
            )
        content = result.stdout if result.stdout else request.context.expected_content
        sandbox.write_text(request.context.expected_artifact, content)
        return ExecutorResult(
            status="succeeded",
            artifacts=(request.context.expected_artifact,),
            usage=_usage(1),
        )


def _usage(attempts: int) -> UsageMetadata:
    return UsageMetadata(
        attempts=attempts,
        tokens=0,
        elapsed_seconds=0.0,
        cost=0.0,
        model_id="",
        executor_id="cursor",
    )


def _subprocess_invoke(
    argv: list[str], env: dict[str, str], cwd: Path, timeout: float
) -> CliResult:
    completed = subprocess.run(  # noqa: S603
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CliResult(completed.returncode, completed.stdout, completed.stderr)
