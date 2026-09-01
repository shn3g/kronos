# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain-English GitHub issue and pull request bodies plus hygiene labels."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from kronos_engine.config.repository import TEMPLATES_ROOT
from kronos_engine.domain.goals import GoalRecord
from kronos_engine.domain.tasks import EvidenceLocator, TaskNode, TaskRecord

_KIND_FIX = ("fix", "bug", "repair")
_KIND_CHORE = ("chore", "docs", "refactor")


def kind_from_title(title: str) -> str:
    lower = title.casefold()
    if any(token in lower for token in _KIND_FIX):
        return "fix"
    if any(token in lower for token in _KIND_CHORE):
        return "chore"
    return "feature"


def issue_labels(*, kind: str, size: str, risk: str) -> tuple[str, ...]:
    return ("kronos:goal", f"kind:{kind}", f"size:{size}", f"risk:{risk}")


def render_issue_body(goal: GoalRecord, tasks: Sequence[TaskNode]) -> str:
    locators = tuple(locator for node in tasks for locator in node.evidence)
    return _render(
        TEMPLATES_ROOT / "github" / "ISSUE.md",
        {
            "title": goal.title,
            "success_criteria": goal.success_criteria,
            "non_goals": goal.non_goals,
            "evidence": _evidence_text(locators),
        },
    )


def render_pull_request_body(goal: GoalRecord, task: TaskRecord) -> str:
    return _render(
        TEMPLATES_ROOT / "github" / "PULL_REQUEST.md",
        {
            "title": task.title,
            "success_criteria": goal.success_criteria,
            "non_goals": goal.non_goals,
            "evidence": _evidence_text(task.evidence),
        },
    )


def _evidence_text(locators: Iterable[EvidenceLocator]) -> str:
    items = [f"{item.path}:{item.line}" for item in locators]
    if not items:
        return "None recorded."
    return "\n".join(f"- {item}" for item in items)


def _render(path: Path, values: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text
