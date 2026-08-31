# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite persistence for goals, tasks, runs, and budget meters."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import replace

from kronos_engine.domain.budgets import BudgetMeter
from kronos_engine.domain.entities import GoalId, RepositoryId, RunId, TaskId
from kronos_engine.domain.goals import GoalRecord, GoalSource, GoalState
from kronos_engine.domain.tasks import (
    EvidenceLocator,
    RunRecord,
    TaskKind,
    TaskRecord,
    TaskState,
)


class SqliteGoalStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_goal(self, goal: GoalRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO goals(
                id, repository_id, title, success_criteria, non_goals, risk_ceiling,
                source, schedule, state, stop_reason, created_at, max_attempts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                success_criteria = excluded.success_criteria,
                non_goals = excluded.non_goals,
                risk_ceiling = excluded.risk_ceiling,
                source = excluded.source,
                schedule = excluded.schedule,
                state = excluded.state,
                stop_reason = excluded.stop_reason,
                max_attempts = excluded.max_attempts
            """,
            (
                goal.id.value,
                goal.repository_id.value,
                goal.title,
                goal.success_criteria,
                goal.non_goals,
                goal.risk_ceiling,
                goal.source.value,
                goal.schedule,
                goal.state.value,
                goal.stop_reason,
                goal.created_at,
                goal.max_attempts,
            ),
        )
        self._conn.commit()

    def get_goal(self, goal_id: GoalId) -> GoalRecord:
        row = self._conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id.value,)).fetchone()
        if row is None:
            raise LookupError(f"goal not found: {goal_id.value}")
        return _goal_from_row(row)

    def list_goals(self) -> Sequence[GoalRecord]:
        rows = self._conn.execute("SELECT * FROM goals ORDER BY created_at, id").fetchall()
        return tuple(_goal_from_row(row) for row in rows)

    def save_task(self, task: TaskRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO tasks(
                id, goal_id, repository_id, title, kind, depends_on_json, evidence_json,
                size, baseline_size, risk, scope_paths_json, exemption, state, stop_reason,
                claimed_by, fence_token, worktree_path, pr_number, pr_url, pr_base,
                head_sha, artifacts_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                kind = excluded.kind,
                depends_on_json = excluded.depends_on_json,
                evidence_json = excluded.evidence_json,
                size = excluded.size,
                baseline_size = excluded.baseline_size,
                risk = excluded.risk,
                scope_paths_json = excluded.scope_paths_json,
                exemption = excluded.exemption,
                state = excluded.state,
                stop_reason = excluded.stop_reason,
                claimed_by = excluded.claimed_by,
                fence_token = excluded.fence_token,
                worktree_path = excluded.worktree_path,
                pr_number = excluded.pr_number,
                pr_url = excluded.pr_url,
                pr_base = excluded.pr_base,
                head_sha = excluded.head_sha,
                artifacts_json = excluded.artifacts_json
            """,
            (
                task.id.value,
                task.goal_id.value,
                task.repository_id.value,
                task.title,
                task.kind.value,
                json.dumps([item.value for item in task.depends_on]),
                json.dumps([{"path": item.path, "line": item.line} for item in task.evidence]),
                task.size,
                task.baseline_size,
                task.risk,
                json.dumps(list(task.scope_paths)),
                task.exemption,
                task.state.value,
                task.stop_reason,
                task.claimed_by,
                task.fence_token,
                task.worktree_path,
                task.pr_number,
                task.pr_url,
                task.pr_base,
                task.head_sha,
                json.dumps(list(task.artifacts)),
            ),
        )
        self._conn.commit()

    def get_task(self, task_id: TaskId) -> TaskRecord:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id.value,)).fetchone()
        if row is None:
            raise LookupError(f"task not found: {task_id.value}")
        return _task_from_row(row)

    def list_tasks(self, goal_id: GoalId | None = None) -> Sequence[TaskRecord]:
        if goal_id is None:
            rows = self._conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE goal_id = ? ORDER BY id", (goal_id.value,)
            ).fetchall()
        return tuple(_task_from_row(row) for row in rows)

    def count_wip(self, repository_id: RepositoryId, states: Sequence[TaskState]) -> int:
        placeholders = ",".join("?" for _ in states)
        params: list[object] = [repository_id.value, *[item.value for item in states]]
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM tasks "
            f"WHERE repository_id = ? AND state IN ({placeholders})",
            params,
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    def save_run(self, run: RunRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO runs(id, goal_id, task_id, status, evidence, pr_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                evidence = excluded.evidence,
                pr_url = excluded.pr_url
            """,
            (
                run.id.value,
                run.goal_id.value,
                run.task_id.value,
                run.status,
                run.evidence,
                run.pr_url,
                run.created_at,
            ),
        )
        self._conn.commit()

    def list_runs(self) -> Sequence[RunRecord]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY created_at, id").fetchall()
        return tuple(_run_from_row(row) for row in rows)

    def budget_meter(self, repository_id: RepositoryId, day: str) -> BudgetMeter:
        row = self._conn.execute(
            "SELECT * FROM budget_meters WHERE repository_id = ? AND day = ?",
            (repository_id.value, day),
        ).fetchone()
        if row is None:
            return BudgetMeter(
                attempts=0,
                daily_dispatches=0,
                consecutive_failures=0,
                breaker_open=False,
                day=day,
            )
        return BudgetMeter(
            attempts=0,
            daily_dispatches=int(row["daily_dispatches"]),
            consecutive_failures=int(row["consecutive_failures"]),
            breaker_open=bool(row["breaker_open"]),
            day=day,
        )

    def save_budget_meter(self, repository_id: RepositoryId, meter: BudgetMeter) -> None:
        self._conn.execute(
            """
            INSERT INTO budget_meters(
                repository_id, day, daily_dispatches, consecutive_failures, breaker_open
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, day) DO UPDATE SET
                daily_dispatches = excluded.daily_dispatches,
                consecutive_failures = excluded.consecutive_failures,
                breaker_open = excluded.breaker_open
            """,
            (
                repository_id.value,
                meter.day,
                meter.daily_dispatches,
                meter.consecutive_failures,
                1 if meter.breaker_open else 0,
            ),
        )
        self._conn.commit()

    def list_budget_meters(self) -> Sequence[tuple[str, BudgetMeter]]:
        rows = self._conn.execute(
            "SELECT repository_id, day, daily_dispatches, consecutive_failures, breaker_open "
            "FROM budget_meters ORDER BY repository_id, day"
        ).fetchall()
        return tuple(
            (
                str(row["repository_id"]),
                BudgetMeter(
                    attempts=0,
                    daily_dispatches=int(row["daily_dispatches"]),
                    consecutive_failures=int(row["consecutive_failures"]),
                    breaker_open=bool(row["breaker_open"]),
                    day=row["day"],
                ),
            )
            for row in rows
        )

    def task_attempts(self, task_id: TaskId) -> int:
        row = self._conn.execute(
            "SELECT attempts FROM task_attempts WHERE task_id = ?", (task_id.value,)
        ).fetchone()
        return int(row["attempts"]) if row is not None else 0

    def set_task_attempts(self, task_id: TaskId, attempts: int) -> None:
        self._conn.execute(
            """
            INSERT INTO task_attempts(task_id, attempts) VALUES (?, ?)
            ON CONFLICT(task_id) DO UPDATE SET attempts = excluded.attempts
            """,
            (task_id.value, attempts),
        )
        self._conn.commit()

    def replace_task(self, task: TaskRecord, **changes: object) -> TaskRecord:
        updated = replace(task, **changes)  # type: ignore[arg-type]
        self.save_task(updated)
        return updated


def _goal_from_row(row: sqlite3.Row) -> GoalRecord:
    return GoalRecord(
        id=GoalId(row["id"]),
        repository_id=RepositoryId(row["repository_id"]),
        title=row["title"],
        success_criteria=row["success_criteria"],
        non_goals=row["non_goals"],
        risk_ceiling=row["risk_ceiling"],
        source=GoalSource(row["source"]),
        state=GoalState(row["state"]),
        max_attempts=int(row["max_attempts"]) if "max_attempts" in row.keys() else 3,
        schedule=row["schedule"],
        stop_reason=row["stop_reason"],
        created_at=row["created_at"],
    )


def _task_from_row(row: sqlite3.Row) -> TaskRecord:
    depends = json.loads(row["depends_on_json"])
    evidence = json.loads(row["evidence_json"])
    scope = json.loads(row["scope_paths_json"])
    artifacts = json.loads(row["artifacts_json"])
    return TaskRecord(
        id=TaskId(row["id"]),
        goal_id=GoalId(row["goal_id"]),
        repository_id=RepositoryId(row["repository_id"]),
        title=row["title"],
        kind=TaskKind(row["kind"]),
        depends_on=tuple(TaskId(item) for item in depends),
        evidence=tuple(
            EvidenceLocator(path=item["path"], line=int(item["line"])) for item in evidence
        ),
        size=row["size"],
        baseline_size=row["baseline_size"],
        risk=row["risk"],
        scope_paths=tuple(scope),
        state=TaskState(row["state"]),
        exemption=row["exemption"],
        stop_reason=row["stop_reason"],
        claimed_by=row["claimed_by"],
        fence_token=row["fence_token"],
        worktree_path=row["worktree_path"],
        pr_number=row["pr_number"],
        pr_url=row["pr_url"],
        pr_base=row["pr_base"],
        head_sha=row["head_sha"],
        artifacts=tuple(artifacts),
    )


def _run_from_row(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=RunId(row["id"]),
        goal_id=GoalId(row["goal_id"]),
        task_id=TaskId(row["task_id"]),
        status=row["status"],
        evidence=row["evidence"],
        pr_url=row["pr_url"],
        created_at=row["created_at"],
    )
