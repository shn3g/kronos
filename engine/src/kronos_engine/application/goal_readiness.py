# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain-language checks for whether a draft goal can run unattended."""

from __future__ import annotations

from dataclasses import dataclass

from kronos_engine.application.safety import SAFETY_CHECK_IDS, SafetyReport
from kronos_engine.domain.budgets import BudgetMeter
from kronos_engine.domain.entities import EnrolledRepository, RepositoryStatus
from kronos_engine.domain.policy import PolicyError, requires_pr_safety
from kronos_engine.ports.forge import GithubAppStatus, GithubConnectionStatus
from kronos_engine.ports.model_registry import RoleAssignments

_SAFETY_LABELS = {
    "ruleset_strict": "Ruleset",
    "kronos_pr_workflow": "Kronos PR workflow",
    "codeowners": "CODEOWNERS",
    "reviewer_app": "Reviewer app",
}


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    id: str
    label: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class GoalReadiness:
    checks: tuple[ReadinessCheck, ...]
    can_execute: bool


def evaluate_goal_readiness(
    record: EnrolledRepository,
    *,
    assignments: RoleAssignments,
    safety: SafetyReport | None,
    github_status: GithubConnectionStatus,
    meter: BudgetMeter,
) -> GoalReadiness:
    checks = (
        _workspace_check(record),
        _models_check(assignments),
        _mode_check(record),
        _github_app_check(
            "github_controller",
            "GitHub controller",
            github_status.controller,
        ),
        _github_app_check("reviewer_app", "Reviewer app", github_status.reviewer),
        *_safety_checks(safety),
        _budget_check(meter),
    )
    can_execute = all(item.ok for item in checks)
    return GoalReadiness(checks=checks, can_execute=can_execute)


def _workspace_check(record: EnrolledRepository) -> ReadinessCheck:
    ok = record.status is RepositoryStatus.ACTIVE
    detail = "Workspace is active." if ok else "Workspace is not active. Open a git folder."
    return ReadinessCheck(id="workspace_active", label="Workspace", ok=ok, detail=detail)


def _models_check(assignments: RoleAssignments) -> ReadinessCheck:
    missing = [
        role
        for role, value in (
            ("planner", assignments.planner),
            ("coder", assignments.coder),
            ("reviewer", assignments.reviewer),
        )
        if not value
    ]
    ok = not missing
    if ok:
        detail = "Planner, coder, and reviewer are assigned."
    else:
        detail = "Assign " + ", ".join(missing) + " on the Models page."
    return ReadinessCheck(id="models_assigned", label="Models assigned", ok=ok, detail=detail)


def _mode_check(record: EnrolledRepository) -> ReadinessCheck:
    mode = record.policy.autonomy.mode
    frozen = record.policy.autonomy.freeze
    try:
        allows = requires_pr_safety(mode)
    except PolicyError:
        allows = False
    ok = allows and not frozen
    if frozen:
        detail = "Autonomy is frozen."
    elif not allows:
        detail = (
            f"Autonomy mode is {mode}. It must be write_draft_prs or higher."
        )
    else:
        detail = "Mode allows writes."
    return ReadinessCheck(id="mode_allows_writes", label="Mode allows writes", ok=ok, detail=detail)


def _github_app_check(check_id: str, label: str, status: GithubAppStatus) -> ReadinessCheck:
    ok = status.verified
    if ok:
        detail = "verified."
    else:
        detail = "not verified. Open Settings → Connections."
    return ReadinessCheck(id=check_id, label=label, ok=ok, detail=detail)


def _safety_checks(safety: SafetyReport | None) -> tuple[ReadinessCheck, ...]:
    by_id = {item.id: item for item in safety.checks} if safety is not None else {}
    checks: list[ReadinessCheck] = []
    for check_id in SAFETY_CHECK_IDS:
        item = by_id.get(check_id)
        if item is None:
            checks.append(
                ReadinessCheck(
                    id=check_id,
                    label=_SAFETY_LABELS.get(check_id, check_id),
                    ok=False,
                    detail="Safety checks have not run.",
                )
            )
            continue
        checks.append(
            ReadinessCheck(
                id=item.id,
                label=_SAFETY_LABELS.get(item.id, item.id),
                ok=item.ok,
                detail=item.detail,
            )
        )
    return tuple(checks)


def _budget_check(meter: BudgetMeter) -> ReadinessCheck:
    ok = not meter.breaker_open
    detail = "Breaker is closed." if ok else "The consecutive-failure breaker is open."
    return ReadinessCheck(id="budget", label="Budget", ok=ok, detail=detail)
