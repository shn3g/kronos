# SPDX-License-Identifier: AGPL-3.0-or-later
"""Model routing, limits, and worker secret policy. Pure values. No I/O."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

MODEL_ROLES: tuple[str, ...] = ("planner", "coder", "reviewer", "embedding")

FORBIDDEN_WORKER_SECRET_KEYS = frozenset(
    {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GITHUB_APP_ID",
        "GITHUB_APP_CLIENT_SECRET",
        "GITHUB_APP_PRIVATE_KEY",
        "KRONOS_AUTH_TOKEN",
        "KRONOS_CONTROLLER_TOKEN",
        "KRONOS_REVIEWER_TOKEN",
        "CONTROLLER_APP_PRIVATE_KEY",
        "REVIEWER_APP_PRIVATE_KEY",
    }
)

T = TypeVar("T")


class ModelRoutingError(ValueError):
    """Raised when model selection or role assignment is invalid."""


class UnapprovedFallbackError(ModelRoutingError):
    """Raised when a fallback model is not on the operator-approved list."""


class PaidFallbackRefused(ModelRoutingError):
    """Raised when a paid model would be used as a silent fallback."""


class AttemptLimitExceeded(ValueError):
    """Raised when retries are unlimited or the attempt budget is exhausted."""


class CostCeilingExceeded(ValueError):
    """Raised when an estimated cost exceeds the operator ceiling."""


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    max_tokens: int
    max_attempts: int
    timeout_seconds: float
    cost_ceiling: float

    def __post_init__(self) -> None:
        assert_finite_attempts(self.max_attempts)


@dataclass(frozen=True, slots=True)
class ModelProfile:
    id: str
    display_name: str
    role: str
    provider_id: str
    model_id: str
    billed: bool
    approved_fallbacks: tuple[str, ...]
    limits: ResourceLimits

    def __post_init__(self) -> None:
        if self.role not in MODEL_ROLES:
            raise ModelRoutingError(f"unknown role {self.role}")
        if self.id.strip() == "" or self.model_id.strip() == "":
            raise ModelRoutingError("profile id and model_id are required")


def select_completion_model(
    profile: ModelProfile,
    *,
    fallback_model_id: str | None = None,
    fallback_billed: bool = False,
) -> str:
    if fallback_model_id is None or fallback_model_id == profile.model_id:
        return profile.model_id
    if fallback_model_id not in profile.approved_fallbacks:
        raise UnapprovedFallbackError(
            f"fallback {fallback_model_id!r} is not on the approved list"
        )
    if fallback_billed:
        raise PaidFallbackRefused(
            "refusing paid model fallback; assign the paid model explicitly"
        )
    return fallback_model_id


def assert_finite_attempts(max_attempts: int) -> int:
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise AttemptLimitExceeded("unlimited retries are forbidden")
    return max_attempts


def assert_cost_allowed(limits: ResourceLimits, estimated_cost: float) -> None:
    if estimated_cost > limits.cost_ceiling:
        raise CostCeilingExceeded("estimated cost exceeds the cost ceiling")


def run_bounded_attempts(operation: Callable[[int], T], max_attempts: int) -> tuple[T, int]:
    assert_finite_attempts(max_attempts)
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation(attempt), attempt
        except Exception as error:
            last_error = error
    raise AttemptLimitExceeded("attempt budget exhausted") from last_error


def is_forbidden_secret_key(key: str) -> bool:
    return key.upper() in FORBIDDEN_WORKER_SECRET_KEYS


def strip_worker_secrets(env: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in env.items() if not is_forbidden_secret_key(key)}
