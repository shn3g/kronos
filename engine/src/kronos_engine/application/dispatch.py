# SPDX-License-Identifier: AGPL-3.0-or-later
"""Claim order: freeze, consume, evidence, lease, worktree, worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from kronos_engine.adapters.git.worktrees import GitCacheWorktree
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.domain.budgets import (
    BreakerTripped,
    BudgetExceeded,
    BudgetMeter,
    check_budget,
    consume,
    record_failure,
    record_success,
    should_consume,
)
from kronos_engine.domain.entities import Lease, RepositoryId, RunId, TaskId
from kronos_engine.domain.goals import GoalState, transition_goal
from kronos_engine.domain.models import ResourceLimits, strip_worker_secrets
from kronos_engine.domain.results import LockHeldError, StaleFenceError
from kronos_engine.domain.tasks import (
    EvidenceLocator,
    RunRecord,
    TaskRecord,
    TaskState,
    transition_task,
)
from kronos_engine.domain.workflow import (
    UnresolvedEvidence,
    lease_resource_key,
    require_evidence,
    require_explicit_task_id,
)
from kronos_engine.indexing.service import IndexingService
from kronos_engine.indexing.sparse import SqliteIndexStore
from kronos_engine.memory.promotion import record_outcome
from kronos_engine.ports.executor import (
    Executor,
    ExecutorCapabilities,
    ExecutorContext,
    ExecutorRequest,
)
from kronos_engine.ports.leases import LeaseStore
from kronos_engine.ports.sandbox import Sandbox
from kronos_engine.skills.catalog import SkillCatalog
from kronos_engine.state.goals import SqliteGoalStore


@dataclass(frozen=True, slots=True)
class ClaimResult:
    ok: bool
    steps: tuple[str, ...]
    failed_step: str | None
    reason: str
    budget_consumed: bool
    worktree: Path | None = None
    lease: Lease | None = None
    task_id: TaskId | None = None


@dataclass(frozen=True, slots=True)
class ExecuteResult:
    ok: bool
    artifacts: tuple[str, ...]
    error: str | None
    status: str


class DispatchService:
    def __init__(
        self,
        store: SqliteGoalStore,
        repos: RepositoryService,
        leases: LeaseStore,
        recorder: Recorder,
        indexer: IndexingService,
        executor: Executor,
        sandbox_factory: Callable[[Path], Sandbox],
        cache_root: Path,
        *,
        clock: Callable[[], datetime],
        worktrees: GitCacheWorktree | None = None,
        skills: SkillCatalog | None = None,
    ) -> None:
        self._store = store
        self._repos = repos
        self._leases = leases
        self._recorder = recorder
        self._indexer = indexer
        self._executor = executor
        self._sandbox_factory = sandbox_factory
        self._cache_root = cache_root
        self._clock = clock
        self._worktrees = worktrees or GitCacheWorktree()
        self._skills = skills

    def claim(
        self,
        task_id: TaskId | str | None,
        *,
        dry_run: bool,
        holder_id: str,
    ) -> ClaimResult:
        raw = task_id.value if isinstance(task_id, TaskId) else task_id
        ident = TaskId(require_explicit_task_id(raw))
        task = self._store.get_task(ident)
        repo = self._repos.get(task.repository_id)
        now = self._clock()
        steps: list[str] = []

        if repo.policy.autonomy.freeze or repo.status.value != "active":
            self._recorder.emit(
                "dispatch.refused",
                {"task_id": ident.value, "step": "freeze", "reason": "repository is frozen"},
            )
            return ClaimResult(
                ok=False,
                steps=tuple(steps),
                failed_step="freeze",
                reason="repository is frozen",
                budget_consumed=False,
                task_id=ident,
            )
        steps.append("freeze")

        day = now.date().isoformat()
        meter = self._store.budget_meter(repo.id, day)
        attempts = self._store.task_attempts(ident)
        goal = self._store.get_goal(task.goal_id)
        try:
            check_budget(meter, repo.policy, task_attempts=attempts)
            if attempts >= goal.max_attempts:
                raise BudgetExceeded("per-issue attempt cap reached")
        except (BudgetExceeded, BreakerTripped) as error:
            self._recorder.emit(
                "dispatch.refused",
                {"task_id": ident.value, "step": "budget", "reason": str(error)},
            )
            return ClaimResult(
                ok=False,
                steps=tuple(steps),
                failed_step="budget",
                reason=str(error),
                budget_consumed=False,
                task_id=ident,
            )
        if not dry_run:
            running = self._store.count_wip(
                repo.id, (TaskState.CLAIMED, TaskState.RUNNING, TaskState.AWAITING_GATES)
            )
            if running >= repo.policy.wip.running:
                return ClaimResult(
                    ok=False,
                    steps=tuple(steps),
                    failed_step="budget",
                    reason="running WIP cap reached",
                    budget_consumed=False,
                    task_id=ident,
                )

        shadow = repo.policy.budgets.dry_run_meters
        consumed = should_consume(dry_run=dry_run, shadow_metering=shadow)
        if consumed:
            self._meter(repo.id, ident, meter, dry_run=dry_run, shadow=shadow)
        steps.append("budget")

        try:
            require_evidence(task.kind.value, task.evidence, task.exemption)
            self._assert_dependencies_merged(task)
            resolve_evidence(self._indexer, repo.id.value, task.evidence)
        except (UnresolvedEvidence, LookupError) as error:
            self._recorder.emit(
                "dispatch.refused",
                {"task_id": ident.value, "step": "evidence", "reason": str(error)},
            )
            return ClaimResult(
                ok=False,
                steps=tuple(steps),
                failed_step="evidence",
                reason=str(error),
                budget_consumed=consumed,
                task_id=ident,
            )
        steps.append("evidence")

        if dry_run:
            return ClaimResult(
                ok=True,
                steps=tuple(steps),
                failed_step=None,
                reason="dry-run",
                budget_consumed=consumed,
                task_id=ident,
            )

        area_key = lease_resource_key(repo.id.value, task.scope_paths, ident.value)
        try:
            lease = self._leases.acquire(
                area_key,
                holder_id,
                timedelta(hours=2),
                now=now,
            )
        except LockHeldError as error:
            self._recorder.emit(
                "dispatch.refused",
                {"task_id": ident.value, "step": "lease", "reason": str(error)},
            )
            return ClaimResult(
                ok=False,
                steps=tuple(steps),
                failed_step="lease",
                reason=str(error),
                budget_consumed=True,
                task_id=ident,
            )
        steps.append("lease")

        try:
            worktree = self._worktrees.create(
                Path(repo.realpath), self._cache_root, repo.id, ident
            )
        except RuntimeError as error:
            self._recorder.emit(
                "dispatch.refused",
                {"task_id": ident.value, "step": "worktree", "reason": str(error)},
            )
            return ClaimResult(
                ok=False,
                steps=tuple(steps),
                failed_step="worktree",
                reason=str(error),
                budget_consumed=True,
                lease=lease,
                task_id=ident,
            )
        steps.append("worktree")

        next_state = (
            TaskState.CLAIMED
            if task.state is TaskState.READY
            else transition_task(task.state, TaskState.CLAIMED)
        )
        self._store.save_task(
            replace(
                task,
                state=next_state,
                claimed_by=holder_id,
                fence_token=lease.fence_token,
                worktree_path=str(worktree),
            )
        )
        if goal.state is GoalState.PLANNED:
            activated = replace(goal, state=transition_goal(goal.state, GoalState.ACTIVE))
            self._store.save_goal(activated)
            self._recorder.emit(
                "goal.transitioned",
                {
                    "goal_id": goal.id.value,
                    "from": goal.state.value,
                    "to": GoalState.ACTIVE.value,
                },
            )
        steps.append("worker")
        self._recorder.emit(
            "task.claimed",
            {"task_id": ident.value, "holder_id": holder_id, "steps": list(steps)},
        )
        self._recorder.emit(
            "task.transitioned",
            {"task_id": ident.value, "from": task.state.value, "to": next_state.value},
        )
        return ClaimResult(
            ok=True,
            steps=tuple(steps),
            failed_step=None,
            reason="claimed",
            budget_consumed=True,
            worktree=worktree,
            lease=lease,
            task_id=ident,
        )

    def execute(self, claimed: ClaimResult, *, phase: str = "green") -> ExecuteResult:
        if not claimed.ok or claimed.task_id is None or claimed.worktree is None:
            reason = claimed.reason or "claim required before execute"
            return ExecuteResult(ok=False, artifacts=(), error=reason, status="failed")
        task = self._store.get_task(claimed.task_id)
        token = claimed.lease.fence_token if claimed.lease is not None else task.fence_token
        if token is None:
            return ExecuteResult(ok=False, artifacts=(), error="fence required", status="failed")
        key = lease_resource_key(task.repository_id.value, task.scope_paths, task.id.value)
        try:
            self._leases.assert_fence(key, token, now=self._clock())
        except StaleFenceError as error:
            return ExecuteResult(ok=False, artifacts=(), error=str(error), status="failed")
        running = task
        if task.state is TaskState.CLAIMED:
            running = replace(task, state=transition_task(task.state, TaskState.RUNNING))
            self._store.save_task(running)
            self._recorder.emit(
                "task.transitioned",
                {
                    "task_id": task.id.value,
                    "from": task.state.value,
                    "to": TaskState.RUNNING.value,
                },
            )
        elif task.state is not TaskState.RUNNING:
            return ExecuteResult(
                ok=False,
                artifacts=(),
                error=f"cannot execute from {task.state.value}",
                status="failed",
            )
        self._recorder.emit("run.started", {"task_id": task.id.value, "phase": phase})
        summaries, routed_ids = self._route_skill_summaries(task)
        request = ExecutorRequest(
            repository_id=task.repository_id,
            task_id=task.id,
            worktree=claimed.worktree,
            context=ExecutorContext(
                story=f"{phase}: {task.title}",
                evidence=",".join(f"{item.path}:{item.line}" for item in task.evidence),
                expected_artifact=_expected_artifact(running, phase),
                expected_content="",
                skill_summaries=summaries,
            ),
            capabilities=ExecutorCapabilities(
                network=True,
                secrets=False,
                root=True,
                autonomous_merge=False,
            ),
            limits=ResourceLimits(
                max_tokens=4096,
                max_attempts=3,
                timeout_seconds=120.0,
                cost_ceiling=0.0,
            ),
            worker_env=strip_worker_secrets({"PATH": "/usr/bin", "LANG": "C"}),
        )
        sandbox = self._sandbox_factory(claimed.worktree)
        result = self._executor.run(request, sandbox)
        artifacts = result.artifacts
        self._store.save_task(replace(running, artifacts=artifacts))
        self._store.save_run(
            RunRecord(
                id=RunId(f"run_{task.id.value}"),
                goal_id=task.goal_id,
                task_id=task.id,
                status=result.status,
                evidence=result.error or ",".join(artifacts),
                pr_url=None,
                created_at=self._clock().isoformat(),
            )
        )
        self._recorder.emit(
            "run.completed",
            {"task_id": task.id.value, "status": result.status, "error": result.error or ""},
        )
        self._record_skill_outcomes(task, routed_ids, helpful=result.status == "succeeded")
        if result.status != "succeeded":
            return ExecuteResult(
                ok=False,
                artifacts=artifacts,
                error=result.error or "executor failed",
                status=result.status,
            )
        return ExecuteResult(ok=True, artifacts=artifacts, error=None, status=result.status)

    def record_run_failure(self, task_id: TaskId) -> None:
        task = self._store.get_task(task_id)
        meter = self._store.budget_meter(task.repository_id, self._clock().date().isoformat())
        repo = self._repos.get(task.repository_id)
        updated = record_failure(meter, repo.policy.budgets.breaker_failure_limit)
        self._store.save_budget_meter(task.repository_id, updated)

    def record_run_success(self, task_id: TaskId) -> None:
        task = self._store.get_task(task_id)
        meter = self._store.budget_meter(task.repository_id, self._clock().date().isoformat())
        self._store.save_budget_meter(task.repository_id, record_success(meter))

    def set_run_pr_url(self, task_id: TaskId, pr_url: str) -> None:
        for run in self._store.list_runs():
            if run.task_id == task_id:
                self._store.save_run(replace(run, pr_url=pr_url))

    def _assert_dependencies_merged(self, task: TaskRecord) -> None:
        for dep in task.depends_on:
            parent = self._store.get_task(dep)
            if parent.state is not TaskState.MERGED:
                raise UnresolvedEvidence(f"dependency {dep.value} is not merged")

    def _meter(
        self,
        repository_id: RepositoryId,
        task_id: TaskId,
        meter: BudgetMeter,
        *,
        dry_run: bool,
        shadow: bool,
    ) -> None:
        updated = consume(meter, dry_run=dry_run, shadow_metering=shadow)
        self._store.save_budget_meter(repository_id, updated)
        if should_consume(dry_run=dry_run, shadow_metering=shadow):
            self._store.set_task_attempts(task_id, self._store.task_attempts(task_id) + 1)
            self._recorder.emit(
                "budget.consumed",
                {"task_id": task_id.value, "attempts": self._store.task_attempts(task_id)},
            )

    def _route_skill_summaries(self, task: TaskRecord) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if self._skills is None:
            return (), ()
        routed = self._skills.route(f"{task.title} {task.kind.value}", budget_tokens=200)
        summaries = tuple(f"{item.name}: {item.description}" for item in routed.summaries)
        installed = {item.name: item.id for item in self._skills.list()}
        ids = tuple(installed[item.name] for item in routed.summaries if item.name in installed)
        return summaries, ids

    def _record_skill_outcomes(
        self, task: TaskRecord, skill_ids: tuple[str, ...], *, helpful: bool
    ) -> None:
        if self._skills is None or not skill_ids:
            return
        source_sha = self._indexer.status(task.repository_id.value).commit or ""
        if not source_sha:
            return
        outcome = "helpful" if helpful else "neutral"
        text = f"Task {task.id.value} {outcome} after execute."
        for skill_id in skill_ids:
            record_outcome(
                self._skills,
                skill_id=skill_id,
                source_sha=source_sha,
                outcome=outcome,
                text=text,
                confidence=0.6 if helpful else 0.8,
            )


def resolve_evidence(
    indexer: IndexingService, repository_id: str, locators: tuple[EvidenceLocator, ...]
) -> None:
    status = indexer.status(repository_id)
    if status.commit is None or not status.ready:
        raise UnresolvedEvidence("index has no commit")
    store = SqliteIndexStore(Path(status.index_path) / "index.sqlite3")
    try:
        for locator in locators:
            chunks = store.chunks_for_path(locator.path)
            if not chunks:
                raise UnresolvedEvidence(
                    f"{locator.path} is not in the indexed commit {status.commit}"
                )
            start = min(item.start_line for item in chunks)
            end = max(item.end_line for item in chunks)
            if locator.line < start or locator.line > end:
                raise UnresolvedEvidence(
                    f"{locator.path}:{locator.line} is not in the indexed commit {status.commit}"
                )
    finally:
        store.close()


def _expected_artifact(task: TaskRecord, phase: str) -> str:
    if phase == "red":
        if task.scope_paths:
            stem = Path(task.scope_paths[0]).stem
            return f"tests/test_{stem}.py"
        return f"tests/test_{task.id.value}.py"
    if task.scope_paths:
        return task.scope_paths[0]
    if task.evidence:
        return task.evidence[0].path
    return f"src/{task.id.value}.py"
