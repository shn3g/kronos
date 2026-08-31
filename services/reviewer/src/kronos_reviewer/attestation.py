# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build signed versioned run attestations without hidden reasoning or secrets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kronos_engine.domain.attestations import (
    ATTESTATION_SCHEMA_VERSION,
    CommandOutcome,
    RunAttestation,
    parse_attestation,
    sign_attestation_payload,
)
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME


def build_attestation(
    *,
    run_id: str,
    head_sha: str,
    base_sha: str,
    reviewer_app_id: int,
    commands: Sequence[CommandOutcome],
    risk: str,
    hmac_key: bytes,
    extra: Mapping[str, object] | None = None,
    conclusion: str = "success",
) -> RunAttestation:
    payload: dict[str, object] = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "run_id": run_id,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "check_name": KRONOS_REVIEW_CHECK_NAME,
        "reviewer_app_id": reviewer_app_id,
        "conclusion": conclusion,
        "policy_source": "base",
        "commands": [
            {
                "argv": list(command.argv),
                "exit_code": command.exit_code,
                "sandbox_fresh": command.sandbox_fresh,
            }
            for command in commands
        ],
        "risk": risk,
    }
    if extra:
        payload.update(dict(extra))
    payload["signature"] = sign_attestation_payload(payload, hmac_key)
    return parse_attestation(payload, hmac_key=hmac_key)
