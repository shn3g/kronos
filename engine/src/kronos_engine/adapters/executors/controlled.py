# SPDX-License-Identifier: AGPL-3.0-or-later
"""Controlled open executor for a bounded synthetic task."""

from __future__ import annotations

from kronos_engine.domain.models import assert_finite_attempts
from kronos_engine.ports.executor import ExecutorRequest, ExecutorResult, UsageMetadata
from kronos_engine.ports.sandbox import Sandbox


class ControlledOpenExecutor:
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
        sandbox.worker_environment(request.worker_env)
        sandbox.write_text(request.context.expected_artifact, request.context.expected_content)
        return ExecutorResult(
            status="succeeded",
            artifacts=(request.context.expected_artifact,),
            usage=UsageMetadata(
                attempts=1,
                tokens=0,
                elapsed_seconds=0.0,
                cost=0.0,
                model_id="",
                executor_id="controlled",
            ),
        )
