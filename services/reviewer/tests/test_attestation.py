# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer attestations are signed, versioned, and free of hidden reasoning."""

from __future__ import annotations

import pytest
from kronos_engine.domain.attestations import (
    ATTESTATION_SCHEMA_VERSION,
    AttestationError,
    CommandOutcome,
    parse_attestation,
)
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from tests.support import BASE_SHA, HEAD_SHA, REVIEWER_APP_ID

from kronos_reviewer.attestation import build_attestation

KEY = b"kronos-test-attestation-key"


def test_build_attestation_is_signed_and_versioned() -> None:
    attestation = build_attestation(
        run_id="run-1",
        head_sha=HEAD_SHA,
        base_sha=BASE_SHA,
        reviewer_app_id=REVIEWER_APP_ID,
        commands=(CommandOutcome(argv=("pytest", "-q"), exit_code=0, sandbox_fresh=True),),
        risk="high",
        hmac_key=KEY,
    )
    assert attestation.schema_version == ATTESTATION_SCHEMA_VERSION
    assert attestation.check_name == KRONOS_REVIEW_CHECK_NAME
    assert attestation.policy_source == "base"
    parsed = parse_attestation(
        {
            "schema_version": attestation.schema_version,
            "run_id": attestation.run_id,
            "head_sha": attestation.head_sha,
            "base_sha": attestation.base_sha,
            "check_name": attestation.check_name,
            "reviewer_app_id": attestation.reviewer_app_id,
            "conclusion": attestation.conclusion,
            "policy_source": attestation.policy_source,
            "commands": [
                {
                    "argv": list(item.argv),
                    "exit_code": item.exit_code,
                    "sandbox_fresh": item.sandbox_fresh,
                }
                for item in attestation.commands
            ],
            "risk": attestation.risk,
            "signature": attestation.signature,
        },
        hmac_key=KEY,
    )
    assert parsed.signature == attestation.signature


def test_build_attestation_copies_command_outcomes() -> None:
    attestation = build_attestation(
        run_id="run-1",
        head_sha=HEAD_SHA,
        base_sha=BASE_SHA,
        reviewer_app_id=REVIEWER_APP_ID,
        commands=(CommandOutcome(argv=("pytest", "-q"), exit_code=1, sandbox_fresh=False),),
        risk="high",
        hmac_key=KEY,
        conclusion="failure",
    )
    assert attestation.commands[0].exit_code == 1
    assert attestation.commands[0].sandbox_fresh is False
    assert attestation.commands[0].argv == ("pytest", "-q")


def test_build_attestation_rejects_hidden_reasoning() -> None:
    with pytest.raises(AttestationError, match="forbidden|reasoning"):
        build_attestation(
            run_id="run-1",
            head_sha=HEAD_SHA,
            base_sha=BASE_SHA,
            reviewer_app_id=REVIEWER_APP_ID,
            commands=(
                CommandOutcome(argv=("pytest", "-q"), exit_code=0, sandbox_fresh=True),
            ),
            risk="high",
            hmac_key=KEY,
            extra={"reasoning": "do not store this"},
        )
