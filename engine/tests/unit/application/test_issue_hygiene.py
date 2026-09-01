# SPDX-License-Identifier: AGPL-3.0-or-later
"""Planned M/L goals open labeled issues in write_issues; XS stays cheap."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.test_goal_to_integration_pr import POLICY_OVERRIDE, GoalHarness

from kronos_engine.application.planning import PlanningService
from kronos_engine.config.repository import TEMPLATES_ROOT
from kronos_engine.domain.goals import GoalSource, GoalSpec
from kronos_engine.indexing.service import IndexingService


class _SizedPlanner:
    def __init__(self, size: str) -> None:
        self._size = size

    def plan(self, goal: object) -> dict[str, object]:
        _ = goal
        return {
            "tasks": [
                {
                    "id": "task_add",
                    "title": "fix add",
                    "kind": "implementation",
                    "depends_on": [],
                    "evidence": [{"path": "pkg/math.py", "line": 1}],
                    "size": self._size,
                    "baseline_size": self._size,
                    "risk": "low",
                    "scope_paths": ["pkg/math.py"],
                }
            ]
        }


def _enrol_write_issues(harness: GoalHarness) -> None:
    record = harness.repos.enrol(
        str(harness.repo_root),
        {
            **POLICY_OVERRIDE,
            "autonomy": {
                "freeze": False,
                "invent_issues": False,
                "refill_enabled": False,
                "mode": "write_issues",
            },
        },
    )
    harness.repo_id = record.id
    IndexingService(harness.paths).rebuild(record.id.value, harness.repo_root, record.policy)


def _create_goal(harness: GoalHarness):
    return harness.goals.create(
        GoalSpec(
            repository_id=harness.repo_id,
            title="Add feature for math",
            success_criteria="add(1, 1) == 2",
            non_goals="do not rewrite packaging",
            risk_ceiling="medium",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )


def test_issue_template_has_the_four_headings() -> None:
    body = (TEMPLATES_ROOT / "github" / "ISSUE.md").read_text(encoding="utf-8")
    for heading in ("Scope", "Acceptance criteria", "Evidence", "Out of scope"):
        assert heading in body
    pr = (TEMPLATES_ROOT / "github" / "PULL_REQUEST.md").read_text(encoding="utf-8")
    for heading in ("Scope", "Acceptance criteria", "Evidence", "Out of scope"):
        assert heading in pr


def test_write_issues_creates_labeled_issue_for_m_goal(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    _enrol_write_issues(harness)
    goal = _create_goal(harness)
    planning = PlanningService(
        harness.store,
        harness.repos,
        harness.recorder,
        _SizedPlanner("M"),
        forge=harness.forge,
    )
    planning.plan(goal.id)
    kinds = harness.fixture.logical_action_kinds()
    assert "create_issue" in kinds
    issue = harness.fixture._issues[-1]
    body = str(issue["body"])
    for heading in ("Scope", "Acceptance criteria", "Evidence", "Out of scope"):
        assert heading in body
    labels = {item["name"] if isinstance(item, dict) else str(item) for item in issue["labels"]}
    assert "kronos:goal" in labels
    assert "kind:feature" in labels
    assert "size:M" in labels
    assert "risk:medium" in labels


def test_xs_planned_goal_does_not_create_issue_in_write_issues(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    _enrol_write_issues(harness)
    goal = _create_goal(harness)
    planning = PlanningService(
        harness.store,
        harness.repos,
        harness.recorder,
        _SizedPlanner("XS"),
        forge=harness.forge,
    )
    planning.plan(goal.id)
    assert "create_issue" not in harness.fixture.logical_action_kinds()
    assert harness.fixture.count_issues() == 0
