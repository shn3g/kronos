# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional Cursor CLI executor behind the same fixture contract."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.models import assert_finite_attempts, is_secret_shaped_key
from kronos_engine.ports.executor import ExecutorRequest, ExecutorResult, UsageMetadata
from kronos_engine.ports.sandbox import Sandbox

WhichFn = Callable[[str], str | None]
InvokeFn = Callable[[list[str], dict[str, str], Path, float], "CliResult"]

_DOCUMENTED_BINARY = "cursor-agent"
_HOST_ENV_KEYS = ("SystemRoot", "SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC")


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


def detect_cursor_cli(
    which: WhichFn | None = None, *, environ: Mapping[str, str] | None = None
) -> CursorCli | None:
    if which is not None:
        path = which(_DOCUMENTED_BINARY)
        if path:
            return CursorCli(path=path, name=_DOCUMENTED_BINARY)
        return None
    path = _resolve_trusted_binary(_DOCUMENTED_BINARY, environ=environ)
    if path is None:
        return None
    return CursorCli(path=path, name=_DOCUMENTED_BINARY, version=_probe_version(path))


class CursorExecutor:
    def __init__(self, *, which: WhichFn | None = None, invoke: InvokeFn | None = None) -> None:
        self._which = which
        self._invoke = invoke or _subprocess_invoke

    def detect(self) -> CursorCli | None:
        return detect_cursor_cli(self._which)

    def run(self, request: ExecutorRequest, sandbox: Sandbox) -> ExecutorResult:
        if request.capabilities.autonomous_merge:
            sandbox.authorize_autonomous_merge()
        sandbox.enforce_capabilities(
            network=request.capabilities.network,
            secrets=request.capabilities.secrets,
            root=request.capabilities.root,
        )
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
        artifact = sandbox.resolve(request.context.expected_artifact)
        worker_wrote = artifact.is_file()
        if result.stdout:
            sandbox.write_text(request.context.expected_artifact, result.stdout)
        elif not worker_wrote:
            return ExecutorResult(
                status="failed",
                artifacts=(),
                usage=_usage(1),
                error="cursor CLI wrote no stdout and did not write the artifact",
            )
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


def _resolve_trusted_binary(
    name: str, *, environ: Mapping[str, str] | None = None
) -> str | None:
    env = os.environ if environ is None else environ
    raw_path = env.get("PATH", "")
    sep = ";" if os.name == "nt" else ":"
    names = _candidate_names(name, env)
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        cwd = None
    for entry in raw_path.split(sep):
        if not entry:
            continue
        directory = Path(entry)
        if not directory.is_absolute():
            continue
        try:
            resolved_dir = directory.resolve()
        except OSError:
            continue
        if cwd is not None and resolved_dir == cwd:
            continue
        for candidate_name in names:
            candidate = resolved_dir / candidate_name
            if candidate.is_file():
                return str(candidate)
    return None


def _candidate_names(name: str, env: Mapping[str, str]) -> tuple[str, ...]:
    if os.name != "nt":
        return (name,)
    exts = [ext for ext in env.get("PATHEXT", ".EXE;.BAT;.CMD").split(";") if ext]
    names = [name]
    lower = name.lower()
    for ext in exts:
        if not lower.endswith(ext.lower()):
            names.append(name + ext)
    return tuple(names)


def _probe_version(path: str) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            shell=False,
            cwd=str(Path(path).resolve().parent),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout or completed.stderr or "").strip()
    return text.splitlines()[0] if text else None


def _host_runtime_env() -> dict[str, str]:
    extra: dict[str, str] = {}
    for key in _HOST_ENV_KEYS:
        value = os.environ.get(key)
        if value and not is_secret_shaped_key(key):
            extra[key] = value
    return extra


def _subprocess_invoke(
    argv: list[str], env: dict[str, str], cwd: Path, timeout: float
) -> CliResult:
    merged = {**_host_runtime_env(), **env}
    completed = subprocess.run(  # noqa: S603
        argv,
        cwd=cwd,
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    return CliResult(completed.returncode, completed.stdout, completed.stderr)
