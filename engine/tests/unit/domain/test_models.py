# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain model routing. No I/O."""

from __future__ import annotations

import pytest

from kronos_engine.domain.models import (
    FORBIDDEN_WORKER_SECRET_KEYS,
    MODEL_ROLES,
    AttemptLimitExceeded,
    CostCeilingExceeded,
    ModelProfile,
    PaidFallbackRefused,
    ResourceLimits,
    UnapprovedFallbackError,
    assert_cost_allowed,
    assert_finite_attempts,
    run_bounded_attempts,
    select_completion_model,
    strip_worker_secrets,
)


def _profile(**overrides: object) -> ModelProfile:
    limits = ResourceLimits(
        max_tokens=1024,
        max_attempts=3,
        timeout_seconds=30.0,
        cost_ceiling=0.0,
    )
    values: dict[str, object] = {
        "id": "prof_coder",
        "display_name": "Local coder",
        "role": "coder",
        "provider_id": "prov_ollama",
        "model_id": "llama3",
        "billed": False,
        "approved_fallbacks": ("llama3.1",),
        "limits": limits,
    }
    values.update(overrides)
    return ModelProfile(**values)  # type: ignore[arg-type]


def test_four_engineering_roles_are_explicit() -> None:
    assert MODEL_ROLES == ("planner", "coder", "reviewer", "embedding")


def test_unapproved_fallback_fails_deterministically() -> None:
    profile = _profile()
    with pytest.raises(UnapprovedFallbackError, match="approved"):
        select_completion_model(profile, fallback_model_id="gpt-4", fallback_billed=True)


def test_silent_paid_fallback_fails_even_when_listed() -> None:
    profile = _profile(approved_fallbacks=("gpt-4",))
    with pytest.raises(PaidFallbackRefused, match="paid"):
        select_completion_model(profile, fallback_model_id="gpt-4", fallback_billed=True)


def test_approved_unbilled_fallback_is_allowed() -> None:
    profile = _profile()
    assert (
        select_completion_model(profile, fallback_model_id="llama3.1", fallback_billed=False)
        == "llama3.1"
    )


def test_primary_paid_model_is_allowed_when_assigned_explicitly() -> None:
    profile = _profile(model_id="gpt-4", billed=True, approved_fallbacks=())
    assert select_completion_model(profile) == "gpt-4"


def test_unlimited_retries_fail_deterministically() -> None:
    with pytest.raises(AttemptLimitExceeded, match="unlimited"):
        assert_finite_attempts(0)
    with pytest.raises(AttemptLimitExceeded, match="unlimited"):
        ResourceLimits(
            max_tokens=1,
            max_attempts=0,
            timeout_seconds=1.0,
            cost_ceiling=0.0,
        )


def test_bounded_attempts_stop_at_the_ceiling() -> None:
    calls = {"n": 0}

    def fail(_attempt: int) -> str:
        calls["n"] += 1
        raise RuntimeError("retry")

    with pytest.raises(AttemptLimitExceeded):
        run_bounded_attempts(fail, max_attempts=3)
    assert calls["n"] == 3


def test_cost_ceiling_blocks_overspend() -> None:
    limits = ResourceLimits(
        max_tokens=1, max_attempts=1, timeout_seconds=1.0, cost_ceiling=0.0
    )
    with pytest.raises(CostCeilingExceeded):
        assert_cost_allowed(limits, estimated_cost=0.01)


def test_worker_secret_keys_include_controller_and_reviewer_leaks() -> None:
    leaked = strip_worker_secrets(
        {
            "PATH": "/bin",
            "GH_TOKEN": "ghp_leak",
            "KRONOS_AUTH_TOKEN": "install",
            "KRONOS_CONTROLLER_TOKEN": "c",
            "KRONOS_REVIEWER_TOKEN": "r",
            "GITHUB_APP_PRIVATE_KEY": "pk",
        }
    )
    assert leaked == {"PATH": "/bin"}
    assert "GH_TOKEN" in FORBIDDEN_WORKER_SECRET_KEYS
    assert "KRONOS_CONTROLLER_TOKEN" in FORBIDDEN_WORKER_SECRET_KEYS
    assert "KRONOS_REVIEWER_TOKEN" in FORBIDDEN_WORKER_SECRET_KEYS
