# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task graph schema, states, and cycle detection. No I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from kronos_engine.domain.entities import GoalId, RepositoryId, RunId, TaskId
from kronos_engine.domain.goals import InvalidTransition
from kronos_engine.domain.policy import RISK_STEPS, SIZE_STEPS
from kronos_engine.domain.risk import apply_planner_risk, apply_planner_size


class SchemaError(ValueError):
    """Raised when a planner DAG is not schema-valid."""


class CycleError(ValueError):
    """Raised when a task graph contains a cycle."""


class ScopeError(ValueError):
    """Raised when a task touches a locked path prefix."""


class WipExceeded(ValueError):
    """Raised when ready or running WIP caps would be exceeded."""


class TaskState(StrEnum):
    PROPOSED = "proposed"
    READY = "ready"
    CLAIMED = "claimed"
    RUNNING = "running"
    AWAITING_GATES = "awaiting_gates"
    AWAITING_REVIEW = "awaiting_review"
    MERGED = "merged"
    PAUSED = "paused"
    STOPPED = "stopped"


class TaskKind(StrEnum):
    IMPLEMENTATION = "implementation"
    DOCS = "docs"
    CONFIG = "config"


TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PROPOSED: frozenset({TaskState.READY, TaskState.STOPPED}),
    TaskState.READY: frozenset({TaskState.CLAIMED, TaskState.PAUSED, TaskState.STOPPED}),
    TaskState.CLAIMED: frozenset(
        {TaskState.RUNNING, TaskState.READY, TaskState.PAUSED, TaskState.STOPPED}
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.AWAITING_GATES,
            TaskState.PAUSED,
            TaskState.STOPPED,
            TaskState.READY,
        }
    ),
    TaskState.AWAITING_GATES: frozenset(
        {
            TaskState.AWAITING_REVIEW,
            TaskState.RUNNING,
            TaskState.PAUSED,
            TaskState.STOPPED,
        }
    ),
    TaskState.AWAITING_REVIEW: frozenset(
        {TaskState.MERGED, TaskState.PAUSED, TaskState.STOPPED, TaskState.RUNNING}
    ),
    TaskState.MERGED: frozenset(),
    TaskState.PAUSED: frozenset({TaskState.READY, TaskState.STOPPED, TaskState.CLAIMED}),
    TaskState.STOPPED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    path: str
    line: int


@dataclass(frozen=True, slots=True)
class TaskNode:
    id: TaskId
    title: str
    kind: TaskKind
    depends_on: tuple[TaskId, ...]
    evidence: tuple[EvidenceLocator, ...]
    size: str
    baseline_size: str
    risk: str
    scope_paths: tuple[str, ...]
    goal_id: GoalId | None = None
    exemption: str | None = None


@dataclass(frozen=True, slots=True)
class TaskGraph:
    nodes: tuple[TaskNode, ...]


@dataclass(frozen=True, slots=True)
class TaskRecord:
    id: TaskId
    goal_id: GoalId
    repository_id: RepositoryId
    title: str
    kind: TaskKind
    depends_on: tuple[TaskId, ...]
    evidence: tuple[EvidenceLocator, ...]
    size: str
    baseline_size: str
    risk: str
    scope_paths: tuple[str, ...]
    state: TaskState
    exemption: str | None = None
    stop_reason: str | None = None
    claimed_by: str | None = None
    fence_token: int | None = None
    worktree_path: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    pr_base: str | None = None
    head_sha: str | None = None
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: RunId
    goal_id: GoalId
    task_id: TaskId
    status: str
    evidence: str
    pr_url: str | None
    created_at: str


def transition_task(current: TaskState, target: TaskState) -> TaskState:
    if target not in TASK_TRANSITIONS[current]:
        raise InvalidTransition(f"cannot transition task from {current} to {target}")
    return target


def parse_task_graph(raw: object) -> TaskGraph:
    if not isinstance(raw, Mapping):
        raise SchemaError("planner output must be a mapping")
    tasks = raw.get("tasks")
    if not isinstance(tasks, list):
        raise SchemaError("planner output must include a tasks list")
    nodes: list[TaskNode] = []
    seen: set[str] = set()
    for item in tasks:
        nodes.append(_parse_node(item, seen))
    return TaskGraph(nodes=tuple(nodes))


def detect_cycle(graph: TaskGraph) -> None:
    by_id = {node.id.value: node for node in graph.nodes}
    visiting: set[str] = set()
    seen: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in seen:
            return
        if node_id in visiting:
            raise CycleError("task graph contains a cycle")
        visiting.add(node_id)
        node = by_id.get(node_id)
        if node is None:
            raise SchemaError(f"unknown dependency {node_id}")
        for dep in node.depends_on:
            walk(dep.value)
        visiting.remove(node_id)
        seen.add(node_id)

    for node in graph.nodes:
        walk(node.id.value)


def clamp_node(node: TaskNode) -> TaskNode:
    size = apply_planner_size(node.baseline_size, node.size)
    risk = apply_planner_risk(node.risk, node.risk)
    return TaskNode(
        id=node.id,
        title=node.title,
        kind=node.kind,
        depends_on=node.depends_on,
        evidence=node.evidence,
        size=size,
        baseline_size=node.baseline_size,
        risk=risk,
        scope_paths=node.scope_paths,
        goal_id=node.goal_id,
        exemption=node.exemption,
    )


def assert_scope_unlocked(scope_paths: Sequence[str], locked_prefixes: Sequence[str]) -> None:
    for path in scope_paths:
        posix = path.replace("\\", "/")
        for prefix in locked_prefixes:
            locked = prefix.replace("\\", "/").rstrip("/")
            if posix == locked or posix.startswith(f"{locked}/"):
                raise ScopeError(f"scope path {posix} is locked")


def _parse_node(raw: object, seen: set[str]) -> TaskNode:
    if not isinstance(raw, Mapping):
        raise SchemaError("task must be a mapping")
    ident = raw.get("id")
    if not isinstance(ident, str) or ident.strip() == "":
        raise SchemaError("task id is required")
    if ident in seen:
        raise SchemaError(f"duplicate task id {ident}")
    seen.add(ident)
    title = raw.get("title")
    if not isinstance(title, str) or title.strip() == "":
        raise SchemaError("task title is required")
    kind_raw = raw.get("kind")
    if kind_raw not in {item.value for item in TaskKind}:
        raise SchemaError("task kind is required")
    depends_raw = raw.get("depends_on")
    if not isinstance(depends_raw, list) or any(not isinstance(item, str) for item in depends_raw):
        raise SchemaError("depends_on must be a list of strings")
    evidence_raw = raw.get("evidence")
    if not isinstance(evidence_raw, list):
        raise SchemaError("evidence is required")
    evidence = tuple(_parse_evidence(item) for item in evidence_raw)
    size = _require_step(raw, "size", SIZE_STEPS)
    baseline = _require_step(raw, "baseline_size", SIZE_STEPS)
    risk = _require_step(raw, "risk", RISK_STEPS)
    scope_raw = raw.get("scope_paths")
    if not isinstance(scope_raw, list) or any(not isinstance(item, str) for item in scope_raw):
        raise SchemaError("scope_paths must be a list of strings")
    exemption = raw.get("exemption")
    if exemption is not None and not isinstance(exemption, str):
        raise SchemaError("exemption must be a string")
    return clamp_node(
        TaskNode(
            id=TaskId(ident),
            title=title,
            kind=TaskKind(str(kind_raw)),
            depends_on=tuple(TaskId(item) for item in depends_raw),
            evidence=evidence,
            size=size,
            baseline_size=baseline,
            risk=risk,
            scope_paths=tuple(scope_raw),
            exemption=exemption,
        )
    )


def _parse_evidence(raw: object) -> EvidenceLocator:
    if not isinstance(raw, Mapping):
        raise SchemaError("evidence locator must be a mapping")
    path = raw.get("path")
    line = raw.get("line")
    if not isinstance(path, str) or path.strip() == "":
        raise SchemaError("evidence path is required")
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        raise SchemaError("evidence line must be a positive integer")
    return EvidenceLocator(path=path.replace("\\", "/"), line=line)


def _require_step(raw: Mapping[str, object], key: str, steps: tuple[str, ...]) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or value not in steps:
        raise SchemaError(f"{key} must be one of {steps}")
    return value
