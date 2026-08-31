# SPDX-License-Identifier: AGPL-3.0-or-later
"""Attempt, daily, and breaker meters. Check is separate from consume. No I/O."""

from __future__ import annotations

from dataclasses import dataclass, replace

from kronos_engine.domain.policy import RepositoryPolicy


class BudgetExceeded(RuntimeError):
    """Raised when a per-task or daily dispatch cap is reached."""


class BreakerTripped(RuntimeError):
    """Raised when the consecutive-failure breaker is open."""


@dataclass(frozen=True, slots=True)
class BudgetMeter:
    attempts: int
    daily_dispatches: int
    consecutive_failures: int
    breaker_open: bool
    day: str


def check_budget(meter: BudgetMeter, policy: RepositoryPolicy, *, task_attempts: int) -> None:
    if meter.breaker_open:
        raise BreakerTripped("consecutive-failure breaker is open")
    if task_attempts >= policy.budgets.max_attempts_per_issue:
        raise BudgetExceeded("per-issue attempt cap reached")
    if meter.daily_dispatches >= policy.budgets.max_dispatches_per_day:
        raise BudgetExceeded("daily dispatch cap reached")


def should_consume(*, dry_run: bool, shadow_metering: bool) -> bool:
    if dry_run:
        return shadow_metering
    return True


def consume(meter: BudgetMeter, *, dry_run: bool, shadow_metering: bool) -> BudgetMeter:
    if not should_consume(dry_run=dry_run, shadow_metering=shadow_metering):
        return meter
    return replace(
        meter,
        attempts=meter.attempts + 1,
        daily_dispatches=meter.daily_dispatches + 1,
    )


def record_failure(meter: BudgetMeter, limit: int) -> BudgetMeter:
    consecutive = meter.consecutive_failures + 1
    return replace(
        meter,
        consecutive_failures=consecutive,
        breaker_open=consecutive >= limit,
    )


def record_success(meter: BudgetMeter) -> BudgetMeter:
    return replace(meter, consecutive_failures=0, breaker_open=False)


def reset_breaker(meter: BudgetMeter) -> BudgetMeter:
    return replace(meter, consecutive_failures=0, breaker_open=False)
