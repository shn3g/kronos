# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import replace
from datetime import date

from kronos_engine.application.goal_readiness import evaluate_goal_readiness
from kronos_engine.application.safety import SAFETY_CHECK_IDS, SafetyCheck, SafetyReport
from kronos_engine.domain.budgets import BudgetMeter
from kronos_engine.domain.entities import EnrolledRepository, RepositoryId, RepositoryStatus
from kronos_engine.domain.policy import default_policy
from kronos_engine.ports.forge import GithubAppStatus, GithubConnectionStatus
from kronos_engine.ports.model_registry import RoleAssignments


def _policy(*, mode: str = "write_draft_prs", freeze: bool = False):
    policy = default_policy(integration_branch="main", protected_branch="main")
    return replace(policy, autonomy=replace(policy.autonomy, mode=mode, freeze=freeze))


def _record(
    *,
    status: RepositoryStatus = RepositoryStatus.ACTIVE,
    mode: str = "write_draft_prs",
    freeze: bool = False,
) -> EnrolledRepository:
    return EnrolledRepository(
        id=RepositoryId("repo_alpha"),
        realpath="/tmp/alpha",
        origin="https://github.com/acme/alpha.git",
        display_name="alpha",
        status=status,
        policy=_policy(mode=mode, freeze=freeze),
        enrolled_at="t",
    )


def _assignments(
    *,
    planner: str | None = "p",
    coder: str | None = "c",
    reviewer: str | None = "r",
) -> RoleAssignments:
    return RoleAssignments(
        orchestrator="o",
        planner=planner,
        coder=coder,
        reviewer=reviewer,
        embedding=None,
    )


def _github(*, controller: bool = True, reviewer: bool = True) -> GithubConnectionStatus:
    return GithubConnectionStatus(
        controller=GithubAppStatus(
            registered=controller,
            installed=controller,
            verified=controller,
            app_id=1 if controller else None,
            slug="controller" if controller else None,
        ),
        reviewer=GithubAppStatus(
            registered=reviewer,
            installed=reviewer,
            verified=reviewer,
            app_id=2 if reviewer else None,
            slug="reviewer" if reviewer else None,
        ),
        webhook_enabled=False,
        poll_mode="conditional",
        github_cli_present=False,
    )


def _safety(*, ok: bool = True) -> SafetyReport:
    return SafetyReport(
        ok=ok,
        checks=tuple(
            SafetyCheck(
                id=check_id,
                ok=ok,
                detail="ok" if ok else f"{check_id} failed",
            )
            for check_id in SAFETY_CHECK_IDS
        ),
    )


def _meter(*, breaker_open: bool = False) -> BudgetMeter:
    return BudgetMeter(
        attempts=0,
        daily_dispatches=0,
        consecutive_failures=3 if breaker_open else 0,
        breaker_open=breaker_open,
        day=date(2026, 9, 2).isoformat(),
    )


def test_readiness_all_ok_can_execute() -> None:
    result = evaluate_goal_readiness(
        _record(),
        assignments=_assignments(),
        safety=_safety(),
        github_status=_github(),
        meter=_meter(),
    )
    assert result.can_execute is True
    assert [item.id for item in result.checks] == [
        "workspace_active",
        "models_assigned",
        "mode_allows_writes",
        "github_controller",
        "reviewer_app",
        *SAFETY_CHECK_IDS,
        "budget",
    ]
    assert all(item.ok for item in result.checks)


def test_readiness_missing_models_blocks() -> None:
    result = evaluate_goal_readiness(
        _record(),
        assignments=_assignments(planner=None, reviewer=""),
        safety=_safety(),
        github_status=_github(),
        meter=_meter(),
    )
    models = next(item for item in result.checks if item.id == "models_assigned")
    assert models.ok is False
    assert result.can_execute is False


def test_readiness_observe_mode_and_freeze_block() -> None:
    observe = evaluate_goal_readiness(
        _record(mode="observe"),
        assignments=_assignments(),
        safety=_safety(),
        github_status=_github(),
        meter=_meter(),
    )
    mode = next(item for item in observe.checks if item.id == "mode_allows_writes")
    assert mode.ok is False
    assert observe.can_execute is False

    frozen = evaluate_goal_readiness(
        _record(mode="write_draft_prs", freeze=True),
        assignments=_assignments(),
        safety=_safety(),
        github_status=_github(),
        meter=_meter(),
    )
    frozen_mode = next(item for item in frozen.checks if item.id == "mode_allows_writes")
    assert frozen_mode.ok is False
    assert frozen.can_execute is False


def test_readiness_github_and_safety_fail_closed() -> None:
    result = evaluate_goal_readiness(
        _record(),
        assignments=_assignments(),
        safety=_safety(ok=False),
        github_status=_github(controller=False, reviewer=False),
        meter=_meter(),
    )
    by_id = {item.id: item for item in result.checks}
    assert by_id["github_controller"].ok is False
    reviewer_checks = [item for item in result.checks if item.id == "reviewer_app"]
    assert reviewer_checks[0].ok is False
    assert "Connections" in reviewer_checks[0].detail
    assert by_id["ruleset_strict"].ok is False
    assert result.can_execute is False


def test_readiness_open_breaker_blocks() -> None:
    result = evaluate_goal_readiness(
        _record(),
        assignments=_assignments(),
        safety=_safety(),
        github_status=_github(),
        meter=_meter(breaker_open=True),
    )
    budget = next(item for item in result.checks if item.id == "budget")
    assert budget.ok is False
    assert result.can_execute is False


def test_readiness_inactive_workspace_blocks() -> None:
    result = evaluate_goal_readiness(
        _record(status=RepositoryStatus.PAUSED),
        assignments=_assignments(),
        safety=_safety(),
        github_status=_github(),
        meter=_meter(),
    )
    workspace = next(item for item in result.checks if item.id == "workspace_active")
    assert workspace.ok is False
    assert result.can_execute is False


def test_readiness_without_safety_report_fails_closed() -> None:
    result = evaluate_goal_readiness(
        _record(),
        assignments=_assignments(),
        safety=None,
        github_status=_github(),
        meter=_meter(),
    )
    by_id = {item.id: item for item in result.checks}
    for check_id in SAFETY_CHECK_IDS:
        assert by_id[check_id].ok is False
    assert result.can_execute is False
