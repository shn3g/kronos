# SPDX-License-Identifier: AGPL-3.0-or-later
"""Red-green artifact gate, bounded repair, draft integration PRs, eligible merge."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from kronos_engine.application.merge import MergeRefused, MergeService
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.domain.entities import TaskId
from kronos_engine.domain.goals import GoalState, transition_goal
from kronos_engine.domain.results import StaleFenceError
from kronos_engine.domain.tasks import TaskRecord, TaskState, transition_task
from kronos_engine.domain.workflow import (
    EmptyTestCommands,
    MissingWorktree,
    NoTestStop,
    TddGateError,
    assert_red_green,
    lease_resource_key,
    require_reproduction_artifact,
    require_test_commands,
    require_worktree_path,
)
from kronos_engine.ports.forge import ForgeError, IdempotencyKey, PullRef
from kronos_engine.ports.leases import LeaseStore
from kronos_engine.state.goals import SqliteGoalStore


class GateRunner(Protocol):
    def run(
        self, worktree: Path, commands: tuple[tuple[str, ...], ...]
    ) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    reason: str
    evidence: str


@dataclass(frozen=True, slots=True)
class MergeAttempt:
    ok: bool
    reason: str


class VerificationService:
    def __init__(
        self,
        store: SqliteGoalStore,
        repos: RepositoryService,
        recorder: Recorder,
        forge: object,
        gates: GateRunner,
        leases: LeaseStore,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._repos = repos
        self._recorder = recorder
        self._forge = forge
        self._gates = gates
        self._leases = leases
        self._clock = clock

    def gate(self, task_id: TaskId) -> VerifyResult:
        task = self._store.get_task(task_id)
        try:
            worktree = Path(require_worktree_path(task.worktree_path))
        except MissingWorktree as error:
            return VerifyResult(ok=False, reason=str(error), evidence=str(error))
        try:
            self._assert_fence(task)
        except StaleFenceError as error:
            return VerifyResult(ok=False, reason=str(error), evidence=str(error))
        repo = self._repos.get(task.repository_id)
        try:
            require_test_commands(repo.policy.commands.test)
        except EmptyTestCommands as error:
            return VerifyResult(ok=False, reason=str(error), evidence=str(error))
        results = self._gates.run(worktree, (tuple(repo.policy.commands.test),))
        passed = bool(results) and all(bool(item.get("passed")) for item in results)
        output = str(results[0].get("output") if results else "no gate output")
        if passed:
            return VerifyResult(ok=True, reason="gates passed", evidence=output)
        return VerifyResult(ok=False, reason="failing tests", evidence=output)

    def accept(
        self,
        task_id: TaskId,
        executed: object,
        *,
        red_failed: bool = False,
        re_execute: Callable[[], object] | None = None,
    ) -> VerifyResult:
        ok = bool(getattr(executed, "ok", False))
        artifacts = tuple(getattr(executed, "artifacts", ()) or ())
        error = getattr(executed, "error", None)
        if not ok:
            return VerifyResult(
                ok=False,
                reason=str(error or "executor failed"),
                evidence=str(error or "executor failed"),
            )
        task = self._store.get_task(task_id)
        try:
            require_worktree_path(task.worktree_path)
        except MissingWorktree as error:
            return VerifyResult(ok=False, reason=str(error), evidence=str(error))
        try:
            require_reproduction_artifact(task.kind.value, artifacts, task.exemption)
        except NoTestStop as stopped:
            return VerifyResult(ok=False, reason=str(stopped), evidence="missing reproduction test")
        repo = self._repos.get(task.repository_id)
        try:
            require_test_commands(repo.policy.commands.test)
        except EmptyTestCommands as error:
            return VerifyResult(ok=False, reason=str(error), evidence=str(error))
        last_output = ""
        max_repair = repo.policy.budgets.max_attempts_per_issue
        current = executed
        for attempt in range(max_repair):
            if attempt > 0 and re_execute is not None:
                current = re_execute()
                if not bool(getattr(current, "ok", False)):
                    last_output = str(getattr(current, "error", None) or "repair execute failed")
                    continue
                artifacts = tuple(getattr(current, "artifacts", ()) or artifacts)
            gated = self.gate(task_id)
            last_output = gated.evidence
            try:
                assert_red_green(red_failed=red_failed, green_passed=gated.ok)
            except TddGateError:
                continue
            waiting = replace(
                task,
                artifacts=artifacts,
                state=transition_task(task.state, TaskState.AWAITING_GATES),
            )
            self._store.save_task(waiting)
            self._recorder.emit(
                "task.transitioned",
                {
                    "task_id": task.id.value,
                    "from": task.state.value,
                    "to": TaskState.AWAITING_GATES.value,
                },
            )
            return VerifyResult(ok=True, reason="gates passed", evidence="gates passed")
        return VerifyResult(
            ok=False,
            reason="failing tests after bounded repair",
            evidence=last_output,
        )

    def open_integration_pr(self, task_id: TaskId) -> PullRef:
        task = self._store.get_task(task_id)
        goal = self._store.get_goal(task.goal_id)
        branch = f"kronos/{task.id.value}"
        create_branch = getattr(self._forge, "create_feature_branch")
        create_branch(branch, IdempotencyKey(f"branch:{task.id.value}"))
        open_draft = getattr(self._forge, "open_draft_pr")
        pull = open_draft(
            task.title,
            goal.success_criteria,
            branch,
            IdempotencyKey(f"pr:{task.id.value}"),
        )
        assert isinstance(pull, PullRef)
        reviewed = replace(
            task,
            state=transition_task(task.state, TaskState.AWAITING_REVIEW),
            pr_number=pull.number,
            pr_url=pull.url,
            pr_base=pull.base,
            head_sha=pull.head_sha,
        )
        self._store.save_task(reviewed)
        self._recorder.emit(
            "task.transitioned",
            {
                "task_id": task.id.value,
                "from": task.state.value,
                "to": TaskState.AWAITING_REVIEW.value,
                "pr_url": pull.url,
            },
        )
        return pull

    def merge_if_eligible(self, task_id: TaskId, merge: MergeService) -> MergeAttempt:
        task = self._store.get_task(task_id)
        if task.pr_number is None:
            return MergeAttempt(ok=False, reason="no integration PR")
        try:
            decision = merge.merge_if_eligible(task.pr_number)
        except MergeRefused as error:
            return MergeAttempt(ok=False, reason=str(error))
        except ForgeError as error:
            return MergeAttempt(ok=False, reason=str(error))
        merged = replace(task, state=transition_task(task.state, TaskState.MERGED))
        self._store.save_task(merged)
        self._recorder.emit(
            "task.transitioned",
            {
                "task_id": task.id.value,
                "from": task.state.value,
                "to": TaskState.MERGED.value,
            },
        )
        siblings = self._store.list_tasks(task.goal_id)
        if siblings and all(item.state is TaskState.MERGED for item in siblings):
            goal = self._store.get_goal(task.goal_id)
            if goal.state is GoalState.ACTIVE:
                completed = replace(
                    goal, state=transition_goal(goal.state, GoalState.COMPLETED)
                )
                self._store.save_goal(completed)
                self._recorder.emit(
                    "goal.transitioned",
                    {
                        "goal_id": goal.id.value,
                        "from": goal.state.value,
                        "to": GoalState.COMPLETED.value,
                    },
                )
        return MergeAttempt(ok=True, reason=decision.reason)

    def _assert_fence(self, task: TaskRecord) -> None:
        if task.fence_token is None:
            raise StaleFenceError("fence required")
        key = lease_resource_key(task.repository_id.value, task.scope_paths, task.id.value)
        self._leases.assert_fence(key, task.fence_token, now=self._clock())
