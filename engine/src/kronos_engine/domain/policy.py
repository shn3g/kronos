# SPDX-License-Identifier: AGPL-3.0-or-later
"""Versioned repository policy. Pure values and clamps. No I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

POLICY_SCHEMA_VERSION = 1

SIZE_STEPS: tuple[str, ...] = ("XS", "XS_PLUS", "S", "M", "L")
RISK_STEPS: tuple[str, ...] = ("low", "medium", "high", "critical")
VALUE_STEPS: tuple[str, ...] = ("cosmetic", "normal", "critical")

_ALLOWED_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "branches",
        "commands",
        "autonomy",
        "paths",
        "risk",
        "budgets",
        "wip",
        "executor",
        "indexing",
    }
)
_UNREPRESENTABLE_AUTONOMY = frozenset({"coder_may_merge", "pulse_may_merge"})


class PolicyError(ValueError):
    """Raised when policy data fails the strict schema or a clamp."""


class BudgetWriteRefused(RuntimeError):
    """Budget meters are schema data only until the metering sub-plan."""


@dataclass(frozen=True, slots=True)
class Branches:
    integration: str
    protected: str


@dataclass(frozen=True, slots=True)
class Commands:
    setup: tuple[str, ...]
    test: tuple[str, ...]
    lint: tuple[str, ...]
    build: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Autonomy:
    freeze: bool
    invent_issues: bool
    refill_enabled: bool


@dataclass(frozen=True, slots=True)
class LockedPaths:
    locked_prefixes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    floor: str


@dataclass(frozen=True, slots=True)
class Budgets:
    max_attempts_per_issue: int
    max_dispatches_per_day: int
    breaker_failure_limit: int
    dry_run_meters: bool


@dataclass(frozen=True, slots=True)
class Wip:
    ready: int
    running: int


@dataclass(frozen=True, slots=True)
class ExecutorProfile:
    profile: str
    sandbox: str


@dataclass(frozen=True, slots=True)
class Indexing:
    enabled: bool


@dataclass(frozen=True, slots=True)
class RepositoryPolicy:
    schema_version: int
    branches: Branches
    commands: Commands
    autonomy: Autonomy
    paths: LockedPaths
    risk: RiskPolicy
    budgets: Budgets
    wip: Wip
    executor: ExecutorProfile
    indexing: Indexing


def default_policy(*, integration_branch: str, protected_branch: str) -> RepositoryPolicy:
    return parse_policy(
        {
            "schema_version": POLICY_SCHEMA_VERSION,
            "branches": {"integration": integration_branch, "protected": protected_branch},
            "commands": {"setup": [], "test": [], "lint": [], "build": []},
            "autonomy": {"freeze": True, "invent_issues": False, "refill_enabled": False},
            "paths": {"locked_prefixes": []},
            "risk": {"floor": "low"},
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
    )


def parse_policy(raw: Mapping[str, object]) -> RepositoryPolicy:
    unknown = set(raw) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise PolicyError(f"unknown policy fields: {sorted(unknown)}")
    schema_version = _require_int(raw, "schema_version")
    if schema_version != POLICY_SCHEMA_VERSION:
        raise PolicyError("unsupported schema_version")
    autonomy_raw = _require_mapping(raw, "autonomy")
    forbidden = _UNREPRESENTABLE_AUTONOMY.intersection(autonomy_raw)
    if forbidden:
        raise PolicyError("worker merge fuses are unrepresentable")
    branches = _require_mapping(raw, "branches")
    commands = _require_mapping(raw, "commands")
    paths = _require_mapping(raw, "paths")
    risk = _require_mapping(raw, "risk")
    budgets = _require_mapping(raw, "budgets")
    wip = _require_mapping(raw, "wip")
    executor = _require_mapping(raw, "executor")
    indexing = _require_mapping(raw, "indexing")
    floor = _require_str(risk, "floor")
    if floor not in RISK_STEPS:
        raise PolicyError("unknown risk floor")
    return RepositoryPolicy(
        schema_version=schema_version,
        branches=Branches(
            integration=_require_str(branches, "integration"),
            protected=_require_str(branches, "protected"),
        ),
        commands=Commands(
            setup=_require_str_tuple(commands, "setup"),
            test=_require_str_tuple(commands, "test"),
            lint=_require_str_tuple(commands, "lint"),
            build=_require_str_tuple(commands, "build"),
        ),
        autonomy=Autonomy(
            freeze=_require_bool(autonomy_raw, "freeze"),
            invent_issues=_require_bool(autonomy_raw, "invent_issues"),
            refill_enabled=_require_bool(autonomy_raw, "refill_enabled"),
        ),
        paths=LockedPaths(locked_prefixes=_require_str_tuple(paths, "locked_prefixes")),
        risk=RiskPolicy(floor=floor),
        budgets=Budgets(
            max_attempts_per_issue=_require_positive_int(budgets, "max_attempts_per_issue"),
            max_dispatches_per_day=_require_positive_int(budgets, "max_dispatches_per_day"),
            breaker_failure_limit=_require_positive_int(budgets, "breaker_failure_limit"),
            dry_run_meters=_require_bool(budgets, "dry_run_meters"),
        ),
        wip=Wip(
            ready=_require_positive_int(wip, "ready"),
            running=_require_positive_int(wip, "running"),
        ),
        executor=ExecutorProfile(
            profile=_require_str(executor, "profile"),
            sandbox=_require_str(executor, "sandbox"),
        ),
        indexing=Indexing(enabled=_require_bool(indexing, "enabled")),
    )


def policy_to_dict(policy: RepositoryPolicy) -> dict[str, object]:
    return {
        "schema_version": policy.schema_version,
        "branches": {
            "integration": policy.branches.integration,
            "protected": policy.branches.protected,
        },
        "commands": {
            "setup": list(policy.commands.setup),
            "test": list(policy.commands.test),
            "lint": list(policy.commands.lint),
            "build": list(policy.commands.build),
        },
        "autonomy": {
            "freeze": policy.autonomy.freeze,
            "invent_issues": policy.autonomy.invent_issues,
            "refill_enabled": policy.autonomy.refill_enabled,
        },
        "paths": {"locked_prefixes": list(policy.paths.locked_prefixes)},
        "risk": {"floor": policy.risk.floor},
        "budgets": {
            "max_attempts_per_issue": policy.budgets.max_attempts_per_issue,
            "max_dispatches_per_day": policy.budgets.max_dispatches_per_day,
            "breaker_failure_limit": policy.budgets.breaker_failure_limit,
            "dry_run_meters": policy.budgets.dry_run_meters,
        },
        "wip": {"ready": policy.wip.ready, "running": policy.wip.running},
        "executor": {"profile": policy.executor.profile, "sandbox": policy.executor.sandbox},
        "indexing": {"enabled": policy.indexing.enabled},
    }


def apply_model_proposal(
    current: RepositoryPolicy, proposal: Mapping[str, object]
) -> RepositoryPolicy:
    proposed = parse_policy(proposal)
    if proposed.autonomy != current.autonomy:
        raise PolicyError("models cannot change autonomy")
    if proposed.budgets != current.budgets:
        raise PolicyError("models cannot change budgets")
    if proposed.wip != current.wip:
        raise PolicyError("models cannot change wip")
    if proposed.branches != current.branches:
        raise PolicyError("models cannot change branches")
    risk = RiskPolicy(floor=clamp_risk(current.risk.floor, proposed.risk.floor))
    return replace(proposed, risk=risk)


def clamp_size(baseline: str, proposed: str) -> str:
    base_i = _step_index(SIZE_STEPS, baseline)
    prop_i = _step_index(SIZE_STEPS, proposed)
    if prop_i < base_i:
        return baseline
    if prop_i > base_i + 1:
        return SIZE_STEPS[base_i + 1]
    return proposed


def clamp_risk(current: str, proposed: str) -> str:
    if _step_index(RISK_STEPS, proposed) < _step_index(RISK_STEPS, current):
        return current
    return proposed


def clamp_value(current: str, proposed: str) -> str:
    if _step_index(VALUE_STEPS, proposed) < _step_index(VALUE_STEPS, current):
        return current
    return proposed


def refuse_budget_write(operation: str) -> None:
    raise BudgetWriteRefused(f"budget write refused until metering exists: {operation}")


def _step_index(steps: tuple[str, ...], value: str) -> int:
    try:
        return steps.index(value)
    except ValueError as error:
        raise PolicyError(f"unknown step {value}") from error


def _require_mapping(raw: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise PolicyError(f"{key} must be a mapping")
    return value


def _require_str(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise PolicyError(f"{key} must be a non-empty string")
    return value


def _require_bool(raw: Mapping[str, object], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise PolicyError(f"{key} must be a boolean")
    return value


def _require_int(raw: Mapping[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyError(f"{key} must be an integer")
    return value


def _require_positive_int(raw: Mapping[str, object], key: str) -> int:
    value = _require_int(raw, key)
    if value < 1:
        raise PolicyError(f"{key} must be >= 1")
    return value


def _require_str_tuple(raw: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PolicyError(f"{key} must be a list of strings")
    return tuple(value)
