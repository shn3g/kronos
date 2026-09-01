# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional OpenCode CLI executor behind the same fixture contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kronos_engine.adapters.executors.cursor import (
    InvokeFn,
    WhichFn,
    _resolve_trusted_binary,
    _subprocess_invoke,
)
from kronos_engine.domain.models import assert_finite_attempts
from kronos_engine.ports.executor import ExecutorRequest, ExecutorResult, UsageMetadata
from kronos_engine.ports.sandbox import Sandbox

_DOCUMENTED_BINARY = "opencode"


@dataclass(frozen=True, slots=True)
class OpencodeCli:
    path: str
    name: str
    version: str | None = None


def detect_opencode_cli(
    which: WhichFn | None = None, *, environ: Mapping[str, str] | None = None
) -> OpencodeCli | None:
    if which is not None:
        path = which(_DOCUMENTED_BINARY)
        if path:
            return OpencodeCli(path=path, name=_DOCUMENTED_BINARY)
        return None
    path = _resolve_trusted_binary(_DOCUMENTED_BINARY, environ=environ)
    if path is None:
        return None
    return OpencodeCli(path=path, name=_DOCUMENTED_BINARY)


class OpencodeExecutor:
    def __init__(self, *, which: WhichFn | None = None, invoke: InvokeFn | None = None) -> None:
        self._which = which
        self._invoke = invoke or _subprocess_invoke

    def detect(self) -> OpencodeCli | None:
        return detect_opencode_cli(self._which)

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
                error="opencode CLI was not detected",
            )
        argv = [
            detected.path,
            "run",
            "--dir",
            str(request.worktree),
            "--artifact",
            request.context.expected_artifact,
            request.context.story,
        ]
        result = self._invoke(argv, env, request.worktree, request.limits.timeout_seconds)
        if result.returncode != 0:
            return ExecutorResult(
                status="failed",
                artifacts=(),
                usage=_usage(1),
                error=result.stderr or "opencode CLI failed",
            )
        artifact = sandbox.resolve(request.context.expected_artifact)
        worker_wrote = artifact.is_file() and artifact.stat().st_size > 0
        if worker_wrote:
            return ExecutorResult(
                status="succeeded",
                artifacts=(request.context.expected_artifact,),
                usage=_usage(1),
            )
        if result.stdout:
            sandbox.write_text(request.context.expected_artifact, result.stdout)
        else:
            return ExecutorResult(
                status="failed",
                artifacts=(),
                usage=_usage(1),
                error="opencode CLI wrote no stdout and did not write the artifact",
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
        executor_id="opencode",
    )
