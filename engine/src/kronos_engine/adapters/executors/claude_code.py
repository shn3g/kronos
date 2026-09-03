# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional Claude Code CLI executor behind the same fixture contract."""

from __future__ import annotations

import os
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

_DOCUMENTED_BINARY = "claude"


@dataclass(frozen=True, slots=True)
class ClaudeCodeCli:
    path: str
    name: str
    version: str | None = None


def detect_claude_code_cli(
    which: WhichFn | None = None, *, environ: Mapping[str, str] | None = None
) -> ClaudeCodeCli | None:
    if which is not None:
        path = which(_DOCUMENTED_BINARY)
        if path:
            return ClaudeCodeCli(path=path, name=_DOCUMENTED_BINARY)
        return None
    path = _resolve_trusted_binary(_DOCUMENTED_BINARY, environ=environ)
    if path is None:
        return None
    return ClaudeCodeCli(path=path, name=_DOCUMENTED_BINARY)


class ClaudeCodeExecutor:
    def __init__(
        self,
        *,
        which: WhichFn | None = None,
        invoke: InvokeFn | None = None,
        model_id: str | None = None,
    ) -> None:
        self._which = which
        self._invoke = invoke or _subprocess_invoke
        self._model_id = model_id

    def detect(self) -> ClaudeCodeCli | None:
        return detect_claude_code_cli(self._which)

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
                error="claude CLI was not detected",
            )
        prompt = (
            f"{request.context.story}\n"
            f"Write the expected artifact to {request.context.expected_artifact}"
        )
        argv = [detected.path, "-p", prompt, "--output-format", "text"]
        chosen = (self._model_id or os.environ.get("KRONOS_CLAUDE_MODEL") or "").strip()
        if chosen:
            argv.extend(["--model", chosen])
        result = self._invoke(argv, env, request.worktree, request.limits.timeout_seconds)
        if result.returncode != 0:
            return ExecutorResult(
                status="failed",
                artifacts=(),
                usage=_usage(1),
                error=result.stderr or result.stdout or "claude CLI failed",
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
                error="claude CLI wrote no stdout and did not write the artifact",
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
        executor_id="claude_code",
    )
