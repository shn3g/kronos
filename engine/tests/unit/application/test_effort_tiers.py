# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dispatch ResourceLimits follow the task size effort table."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tests.e2e.test_goal_to_integration_pr import GoalHarness, ScriptedExecutor

from kronos_engine.domain.policy import default_policy, parse_policy, policy_to_dict


class _Capture(ScriptedExecutor):
    def __init__(self) -> None:
        super().__init__("happy")
        self.last = None

    def run(self, request, sandbox):  # type: ignore[no-untyped-def]
        self.last = request
        return super().run(request, sandbox)


def test_old_policy_without_effort_parses_defaults() -> None:
    payload = policy_to_dict(default_policy(integration_branch="main", protected_branch="main"))
    budgets = dict(payload["budgets"])  # type: ignore[arg-type]
    budgets.pop("effort", None)
    payload["budgets"] = budgets
    policy = parse_policy(payload)
    xs = next(item for item in policy.budgets.effort if item.size == "XS")
    medium = next(item for item in policy.budgets.effort if item.size == "M")
    assert xs.max_tokens == 1024
    assert xs.max_attempts == 1
    assert xs.create_issue is False
    assert medium.max_tokens == 4096
    assert medium.max_attempts == 3
    assert medium.create_issue is True


def test_xs_dispatch_uses_tight_limits(tmp_path: Path) -> None:
    capture = _Capture()
    harness = GoalHarness(tmp_path, "happy", executor=capture)
    harness.setup_goal()
    task = harness.store.get_task(harness.task_id)
    harness.store.save_task(replace(task, size="XS"))
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is True
    executed = harness.dispatch.execute(claimed, phase="red")
    assert executed.ok is True
    assert capture.last is not None
    assert capture.last.limits.max_tokens == 1024
    assert capture.last.limits.max_attempts == 1


def test_m_dispatch_uses_standard_limits(tmp_path: Path) -> None:
    capture = _Capture()
    harness = GoalHarness(tmp_path, "happy", executor=capture)
    harness.setup_goal()
    task = harness.store.get_task(harness.task_id)
    harness.store.save_task(replace(task, size="M"))
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is True
    executed = harness.dispatch.execute(claimed, phase="red")
    assert executed.ok is True
    assert capture.last is not None
    assert capture.last.limits.max_tokens == 4096
    assert capture.last.limits.max_attempts == 3
