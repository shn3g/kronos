# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for versioned repository policy. Domain has no I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from kronos_engine.domain.policy import (
    POLICY_SCHEMA_VERSION,
    BudgetWriteRefused,
    PolicyError,
    RepositoryPolicy,
    apply_model_proposal,
    clamp_risk,
    clamp_size,
    clamp_value,
    default_policy,
    parse_policy,
    refuse_budget_write,
)


def test_default_policy_ports_prior_fuses_as_schema_data() -> None:
    policy = default_policy(integration_branch="main", protected_branch="main")
    assert policy.schema_version == POLICY_SCHEMA_VERSION
    assert policy.schema_version == 1
    assert policy.autonomy.freeze is True
    assert policy.autonomy.invent_issues is False
    assert policy.autonomy.refill_enabled is False
    assert policy.wip.ready == 2
    assert policy.wip.running == 3
    assert policy.budgets.max_attempts_per_issue == 3
    assert policy.budgets.max_dispatches_per_day == 12
    assert policy.budgets.breaker_failure_limit == 4
    assert policy.budgets.dry_run_meters is False
    assert policy.branches.integration == "main"
    assert policy.branches.protected == "main"
    assert policy.executor.profile == "standard"
    assert policy.indexing.enabled is True


def test_strict_schema_rejects_unknown_fields_and_worker_merge_fuses() -> None:
    with pytest.raises(PolicyError, match="unknown"):
        parse_policy({"schema_version": 1, "unexpected": True})
    with pytest.raises(PolicyError, match="unrepresentable|merge"):
        parse_policy(
            {
                **_minimal_policy_dict(),
                "autonomy": {
                    "freeze": True,
                    "invent_issues": False,
                    "refill_enabled": False,
                    "coder_may_merge": True,
                },
            }
        )


def test_models_cannot_lower_risk_or_raise_budgets() -> None:
    current = parse_policy(_minimal_policy_dict())
    lowered = _minimal_policy_dict()
    lowered["risk"] = {"floor": "low"}
    with pytest.raises(PolicyError, match="risk"):
        apply_model_proposal(current, lowered)

    raised = _minimal_policy_dict()
    raised["budgets"] = {
        "max_attempts_per_issue": 99,
        "max_dispatches_per_day": 12,
        "breaker_failure_limit": 4,
        "dry_run_meters": False,
    }
    with pytest.raises(PolicyError, match="budget"):
        apply_model_proposal(current, raised)


def test_clamp_size_allows_one_step_up_and_never_shrinks() -> None:
    assert clamp_size("S", "M") == "M"
    assert clamp_size("S", "L") == "M"
    assert clamp_size("M", "XS") == "M"
    assert clamp_size("L", "L") == "L"


def test_clamp_risk_only_moves_up() -> None:
    assert clamp_risk("low", "high") == "high"
    assert clamp_risk("high", "low") == "high"
    assert clamp_risk("critical", "medium") == "critical"


def test_critical_value_cannot_be_downgraded() -> None:
    assert clamp_value("critical", "normal") == "critical"
    assert clamp_value("cosmetic", "normal") == "normal"
    assert clamp_value("normal", "cosmetic") == "normal"


def test_budget_enforcement_refuses_writes_until_metering_exists() -> None:
    with pytest.raises(BudgetWriteRefused, match="refused"):
        refuse_budget_write("consume")


def test_policy_module_has_no_io() -> None:
    import kronos_engine.domain.policy as policy_mod

    assert policy_mod.__file__ is not None
    source = Path(policy_mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "sqlite3", "pathlib", "open(", "yaml", "httpx", "urllib"):
        assert forbidden not in source


def test_operator_can_set_distinct_integration_and_protected_branches() -> None:
    policy = parse_policy(
        {
            **_minimal_policy_dict(),
            "branches": {"integration": "main-openclaw", "protected": "main"},
        }
    )
    assert isinstance(policy, RepositoryPolicy)
    assert policy.branches.integration == "main-openclaw"
    assert policy.branches.protected == "main"


def _minimal_policy_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "branches": {"integration": "main", "protected": "main"},
        "commands": {
            "setup": ["pnpm", "install"],
            "test": ["pnpm", "test"],
            "lint": [],
            "build": [],
        },
        "autonomy": {"freeze": True, "invent_issues": False, "refill_enabled": False},
        "paths": {"locked_prefixes": ["engine/src/kronos_engine/domain"]},
        "risk": {"floor": "high"},
        "budgets": {
            "max_attempts_per_issue": 3,
            "max_dispatches_per_day": 12,
            "breaker_failure_limit": 4,
            "dry_run_meters": False,
        },
        "wip": {"ready": 2, "running": 3},
        "executor": {"profile": "standard", "sandbox": "default"},
        "indexing": {"enabled": True},
    }
