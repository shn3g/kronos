# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic evidence gate for goal completion."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from kronos_engine.domain.tasks import TaskRecord

VERIFICATION_PASSED_ARTIFACT = "verification:gates-passed"
_PASSING_GATE = re.compile(r"\bexit\s+code\s*[:=]?\s*0\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class GoalCompletionDecision:
    allowed: bool
    reason: str


class GoalJudge:
    """Allow completion only when a merged task has durable verification evidence."""

    def decide(self, tasks: Sequence[TaskRecord]) -> GoalCompletionDecision:
        for task in tasks:
            if self._has_passing_gate_evidence(task.artifacts):
                return GoalCompletionDecision(True, "goal completion evidence found")
            if VERIFICATION_PASSED_ARTIFACT in task.artifacts:
                return GoalCompletionDecision(True, "goal completion evidence found")
        return GoalCompletionDecision(False, "goal completion refused: no evidence artifacts")

    @staticmethod
    def _has_passing_gate_evidence(artifacts: Sequence[str]) -> bool:
        return any(_PASSING_GATE.search(artifact) is not None for artifact in artifacts)
