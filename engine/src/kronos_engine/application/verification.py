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
from kronos_engine.domain.goals import GoalState
from kronos_engine.domain.tasks import TaskState, transition_task
from kronos_engine.domain.workflow import NoTestStop, require_reproduction_artifact
from kronos_engine.ports.forge import ForgeError, IdempotencyKey, PullRef
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
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._repos = repos
        self._recorder = recorder
        self._forge = forge
        self._gates = gates
        self._clock = clock

    def accept(self, task_id: TaskId, executed: object) -> VerifyResult:
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
            require_reproduction_artifact(task.kind.value, artifacts, task.exemption)
        except NoTestStop as stopped:
            return VerifyResult(ok=False, reason=str(stopped), evidence="missing reproduction test")
        repo = self._repos.get(task.repository_id)
        commands = tuple(
            group
            for group in (
                repo.policy.commands.setup,
                repo.policy.commands.test,
                repo.policy.commands.lint,
                repo.policy.commands.build,
            )
            if group
        )
        worktree = Path(task.worktree_path or ".")
        last_output = ""
        max_repair = repo.policy.budgets.max_attempts_per_issue
        for _attempt in range(max_repair):
            results = self._gates.run(worktree, commands)
            if all(bool(item.get("passed")) for item in results):
                gated = replace(
                    task,
                    artifacts=artifacts,
                    state=transition_task(task.state, TaskState.AWAITING_GATES),
                )
                self._store.save_task(gated)
                self._recorder.emit(
                    "task.transitioned",
                    {
                        "task_id": task.id.value,
                        "from": task.state.value,
                        "to": TaskState.AWAITING_GATES.value,
                    },
                )
                return VerifyResult(ok=True, reason="gates passed", evidence="gates passed")
            last_output = str(results[0].get("output") if results else "failing tests")
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
                self._store.save_goal(replace(goal, state=GoalState.COMPLETED))
                self._recorder.emit(
                    "goal.transitioned",
                    {
                        "goal_id": goal.id.value,
                        "from": goal.state.value,
                        "to": GoalState.COMPLETED.value,
                    },
                )
        return MergeAttempt(ok=True, reason=decision.reason)
