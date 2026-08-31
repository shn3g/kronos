# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production sequencer: plan, claim, red-green execute, recover, MergeService merge."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from kronos_engine.application.dispatch import ClaimResult, DispatchService
from kronos_engine.application.merge import MergeService
from kronos_engine.application.notifications import NotificationService
from kronos_engine.application.planning import PlanningService
from kronos_engine.application.recovery import RecoveryService
from kronos_engine.application.verification import VerificationService
from kronos_engine.domain.entities import GoalId, RepositoryId, TaskId
from kronos_engine.domain.goals import GoalRecord, GoalState
from kronos_engine.domain.tasks import TaskRecord, TaskState
from kronos_engine.domain.workflow import NoTestStop, require_reproduction_artifact
from kronos_engine.ports.forge import ForgeError, PullRef
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.scheduler import GoalScheduler


@dataclass(frozen=True, slots=True)
class TickResult:
    ok: bool
    status: str
    reason: str
    task_id: str | None
    pr_url: str | None
    claim_steps: tuple[str, ...]
    terminal: bool


class GoalEngine:
    def __init__(
        self,
        store: SqliteGoalStore,
        planning: PlanningService,
        dispatch: DispatchService,
        verification: VerificationService,
        recovery: RecoveryService,
        merge: MergeService,
        scheduler: GoalScheduler,
        *,
        clock: Callable[[], datetime] | None = None,
        notifications: NotificationService | None = None,
    ) -> None:
        self._store = store
        self._planning = planning
        self._dispatch = dispatch
        self._verification = verification
        self._recovery = recovery
        self._merge = merge
        self._scheduler = scheduler
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._notifications = notifications

    def plan(self, goal_id: GoalId) -> object:
        return self._planning.plan(goal_id)

    def get_goal(self, goal_id: GoalId) -> GoalRecord:
        return self._store.get_goal(goal_id)

    def list_tasks(self, goal_id: GoalId) -> Sequence[TaskRecord]:
        return self._store.list_tasks(goal_id)

    def ingest_github_issue(
        self,
        *,
        repository_id: RepositoryId,
        title: str,
        body: str,
        non_goals: str,
        risk_ceiling: str,
        max_attempts: int,
    ) -> GoalRecord:
        created = self._scheduler.ingest_github_issue(
            repository_id=repository_id,
            title=title,
            body=body,
            non_goals=non_goals,
            risk_ceiling=risk_ceiling,
            max_attempts=max_attempts,
        )
        assert isinstance(created, GoalRecord)
        return created

    def ingest_schedule(
        self,
        *,
        repository_id: RepositoryId,
        title: str,
        success_criteria: str,
        non_goals: str,
        schedule: str,
        max_attempts: int,
        risk_ceiling: str = "low",
    ) -> GoalRecord:
        created = self._scheduler.ingest_schedule(
            repository_id=repository_id,
            title=title,
            success_criteria=success_criteria,
            non_goals=non_goals,
            schedule=schedule,
            max_attempts=max_attempts,
            risk_ceiling=risk_ceiling,
        )
        assert isinstance(created, GoalRecord)
        return created

    def tick(self, *, holder_id: str = "engine") -> TickResult:
        now = self._clock()
        for goal in self._scheduler.tick_due(now):
            try:
                self._planning.plan(goal.id)
            except Exception as error:
                return self._plan_failed(error)
        for goal in self._store.list_goals():
            if goal.state is GoalState.DRAFT:
                try:
                    self._planning.plan(goal.id)
                except Exception as error:
                    return self._plan_failed(error)
        ready = self._next_ready_task()
        if ready is None:
            return TickResult(
                ok=True,
                status="idle",
                reason="no ready task",
                task_id=None,
                pr_url=None,
                claim_steps=(),
                terminal=False,
            )
        return self.advance(ready.id, holder_id=holder_id)

    def advance(
        self,
        task_id: TaskId,
        *,
        holder_id: str = "engine",
        after_pr: Callable[[PullRef], None] | None = None,
        stop_after: str | None = None,
    ) -> TickResult:
        claimed = self._dispatch.claim(task_id, dry_run=False, holder_id=holder_id)
        if not claimed.ok:
            if claimed.failed_step != "freeze":
                paused = self._recovery.pause_or_stop(task_id, claimed.reason, claimed.reason)
                self._notify_failure(claimed.reason, claimed.reason)
                return self._from_task(paused, claimed, ok=False, terminal=True)
            return TickResult(
                ok=False,
                status="frozen",
                reason=claimed.reason,
                task_id=task_id.value,
                pr_url=None,
                claim_steps=claimed.steps,
                terminal=False,
            )
        red = self._dispatch.execute(claimed, phase="red")
        if not red.ok:
            return self._fail(task_id, claimed, red.error or "executor failed", trip=True)
        task = self._store.get_task(task_id)
        try:
            require_reproduction_artifact(task.kind.value, red.artifacts, task.exemption)
        except NoTestStop as stopped:
            paused = self._recovery.pause_or_stop(
                task_id, str(stopped), "missing reproduction test"
            )
            return self._from_task(paused, claimed, ok=False, terminal=True)
        red_gate = self._verification.gate(task_id)
        if "empty" in red_gate.reason.lower() or "worktree" in red_gate.reason.lower():
            return self._fail(task_id, claimed, red_gate.reason, trip=False)
        if red_gate.ok:
            return self._fail(task_id, claimed, "TDD red required before accept", trip=False)
        green = self._dispatch.execute(claimed, phase="green")
        if not green.ok:
            return self._fail(task_id, claimed, green.error or "executor failed", trip=True)
        verified = self._verification.accept(
            task_id,
            green,
            red_failed=True,
            re_execute=lambda: self._dispatch.execute(claimed, phase="green"),
        )
        if not verified.ok:
            reason = verified.reason.lower()
            trip = "no-test" not in reason and "reproduction" not in reason
            return self._fail(
                task_id, claimed, verified.reason, trip=trip, evidence=verified.evidence
            )
        try:
            pull = self._verification.open_integration_pr(task_id)
        except (ForgeError, AttributeError, TypeError) as error:
            return self._fail(task_id, claimed, str(error), trip=False)
        self._dispatch.set_run_pr_url(task_id, pull.url)
        if stop_after == "pr":
            task = self._store.get_task(task_id)
            return self._from_task(task, claimed, ok=True, terminal=False)
        if after_pr is not None:
            after_pr(pull)
        merged = self._verification.merge_if_eligible(task_id, self._merge)
        if not merged.ok:
            return self._fail(task_id, claimed, merged.reason, trip=False)
        self._dispatch.record_run_success(task_id)
        task = self._store.get_task(task_id)
        return self._from_task(task, claimed, ok=True, terminal=True)

    def _fail(
        self,
        task_id: TaskId,
        claimed: ClaimResult,
        reason: str,
        *,
        trip: bool,
        evidence: str | None = None,
    ) -> TickResult:
        if trip:
            self._dispatch.record_run_failure(task_id)
        paused = self._recovery.pause_or_stop(task_id, reason, evidence or reason)
        self._notify_failure(reason, evidence)
        return self._from_task(paused, claimed, ok=False, terminal=True)

    def _from_task(
        self, task: TaskRecord, claimed: ClaimResult, *, ok: bool, terminal: bool
    ) -> TickResult:
        return TickResult(
            ok=ok,
            status=task.state.value,
            reason=task.stop_reason or claimed.reason,
            task_id=task.id.value,
            pr_url=task.pr_url,
            claim_steps=claimed.steps,
            terminal=terminal,
        )

    def _next_ready_task(self) -> TaskRecord | None:
        for task in self._store.list_tasks():
            if task.state is not TaskState.READY:
                continue
            if all(self._store.get_task(dep).state is TaskState.MERGED for dep in task.depends_on):
                return task
        return None

    def _plan_failed(self, error: Exception) -> TickResult:
        self._notify_failure(str(error), str(error))
        return TickResult(
            ok=False,
            status="plan_failed",
            reason=str(error),
            task_id=None,
            pr_url=None,
            claim_steps=(),
            terminal=False,
        )

    def _notify_failure(self, reason: str, log_excerpt: str | None = None) -> None:
        if self._notifications is None:
            return
        self._notifications.notify_failure_allowed(reason=reason, log_excerpt=log_excerpt)
