# SPDX-License-Identifier: AGPL-3.0-or-later
"""Executor request/result contract. Worktrees stay under the cache root."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from kronos_engine.domain.entities import RepositoryId, TaskId
from kronos_engine.domain.models import ResourceLimits
from kronos_engine.ports.sandbox import Sandbox


@dataclass(frozen=True, slots=True)
class ExecutorContext:
    story: str
    evidence: str
    expected_artifact: str
    expected_content: str


@dataclass(frozen=True, slots=True)
class ExecutorCapabilities:
    network: bool
    secrets: bool
    root: bool
    autonomous_merge: bool


@dataclass(frozen=True, slots=True)
class ExecutorRequest:
    repository_id: RepositoryId
    task_id: TaskId
    worktree: Path
    context: ExecutorContext
    capabilities: ExecutorCapabilities
    limits: ResourceLimits
    worker_env: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    attempts: int
    tokens: int
    elapsed_seconds: float
    cost: float
    model_id: str
    executor_id: str


@dataclass(frozen=True, slots=True)
class ExecutorResult:
    status: Literal["succeeded", "failed"]
    artifacts: tuple[str, ...]
    usage: UsageMetadata
    error: str | None = None


class Executor(Protocol):
    def run(self, request: ExecutorRequest, sandbox: Sandbox) -> ExecutorResult: ...
