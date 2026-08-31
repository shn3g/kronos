# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared synthetic executor request used by both adapters."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.domain.entities import RepositoryId, TaskId
from kronos_engine.domain.models import ResourceLimits
from kronos_engine.ports.executor import (
    ExecutorCapabilities,
    ExecutorContext,
    ExecutorRequest,
)

SYNTHETIC_ARTIFACT = "artifacts/hello.txt"
SYNTHETIC_CONTENT = "kronos-ok\n"


def synthetic_request(
    worktree: Path,
    *,
    artifact: str = SYNTHETIC_ARTIFACT,
    content: str = SYNTHETIC_CONTENT,
    max_attempts: int = 3,
    worker_env: dict[str, str] | None = None,
    autonomous_merge: bool = False,
) -> ExecutorRequest:
    worktree.mkdir(parents=True, exist_ok=True)
    return ExecutorRequest(
        repository_id=RepositoryId("repo_alpha"),
        task_id=TaskId("task_synthetic"),
        worktree=worktree,
        context=ExecutorContext(
            story="write the fixture artifact",
            evidence="engine/tests/contract/test_executor.py",
            expected_artifact=artifact,
            expected_content=content,
        ),
        capabilities=ExecutorCapabilities(
            network=False,
            secrets=False,
            root=False,
            autonomous_merge=autonomous_merge,
        ),
        limits=ResourceLimits(
            max_tokens=512,
            max_attempts=max_attempts,
            timeout_seconds=30.0,
            cost_ceiling=0.0,
        ),
        worker_env=worker_env or {"PATH": "/usr/bin", "LANG": "C"},
    )
