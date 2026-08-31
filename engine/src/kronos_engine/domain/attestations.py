# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signed run attestations and merge identity. Pure values. No I/O."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.domain.models import is_secret_shaped_key

ATTESTATION_SCHEMA_VERSION = 1
ATTESTATION_HMAC_KEY_REF = "github:reviewer:attestation_key"
POLICY_SOURCE_BASE = "base"
POSTED_BY_REVIEWER = "reviewer"
POSTED_BY_CONTROLLER = "controller"
POSTED_BY_WORKER = "worker"
POSTED_BY_FOREIGN = "foreign"

_ALLOWED_ATTESTATION_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "head_sha",
        "base_sha",
        "check_name",
        "reviewer_app_id",
        "conclusion",
        "policy_source",
        "commands",
        "risk",
        "signature",
    }
)
_FORBIDDEN_ATTESTATION_FIELDS = frozenset(
    {
        "reasoning",
        "chain_of_thought",
        "hidden_reasoning",
        "scratchpad",
        "secrets",
        "secret",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "private_key",
        "pem",
        "identity_satisfied",
    }
)
_ALLOWED_CONCLUSIONS = frozenset({"success", "failure", "cancelled", "neutral", "timed_out"})


class AttestationError(ValueError):
    """Raised when an attestation is malformed, unsigned, or contains secrets."""


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    argv: tuple[str, ...]
    exit_code: int
    sandbox_fresh: bool


@dataclass(frozen=True, slots=True)
class RunAttestation:
    schema_version: int
    run_id: str
    head_sha: str
    base_sha: str
    check_name: str
    reviewer_app_id: int
    conclusion: str
    policy_source: str
    commands: tuple[CommandOutcome, ...]
    risk: str
    signature: str


@dataclass(frozen=True, slots=True)
class CheckRunIdentity:
    name: str
    head_sha: str
    conclusion: str
    app_id: int | None
    app_slug: str | None
    posted_by: str


@dataclass(frozen=True, slots=True)
class CommentEvidence:
    body: str
    author_login: str
    author_type: str = "User"


@dataclass(frozen=True, slots=True)
class MergeEvidence:
    pr_head_sha: str
    base_branch: str
    integration_branch: str
    protected_branch: str
    labels: tuple[str, ...]
    comments: tuple[CommentEvidence, ...]
    checks: tuple[CheckRunIdentity, ...]
    review_threads_resolved: bool
    ruleset_strict: bool
    expected_reviewer_app_id: int
    policy_source: str
    commands_rerun_in_fresh_sandbox: bool
    required_commands: tuple[tuple[str, ...], ...]
    attestation: RunAttestation | None
    freeze: bool = False


@dataclass(frozen=True, slots=True)
class MergeDecision:
    allowed: bool
    reason: str
    target: str = ""


def sign_attestation_payload(payload: Mapping[str, object], hmac_key: bytes) -> str:
    body = {key: value for key, value in payload.items() if key != "signature"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(hmac_key, canonical, hashlib.sha256).hexdigest()


def parse_attestation(raw: Mapping[str, object], *, hmac_key: bytes) -> RunAttestation:
    unknown = set(raw) - _ALLOWED_ATTESTATION_FIELDS
    forbidden = unknown | (_FORBIDDEN_ATTESTATION_FIELDS.intersection(raw))
    secret_keys = {key for key in raw if is_secret_shaped_key(str(key))}
    if forbidden or secret_keys:
        names = sorted(forbidden | secret_keys)
        raise AttestationError(f"forbidden attestation field: {names[0]}")
    schema_version = raw.get("schema_version")
    if schema_version != ATTESTATION_SCHEMA_VERSION:
        raise AttestationError("unsupported attestation schema_version")
    signature = raw.get("signature")
    if not isinstance(signature, str) or signature == "":
        raise AttestationError("signature is required")
    expected = sign_attestation_payload(raw, hmac_key)
    if not hmac.compare_digest(expected, signature):
        raise AttestationError("signature is invalid")
    commands_raw = raw.get("commands")
    if not isinstance(commands_raw, list):
        raise AttestationError("commands must be a list")
    commands = tuple(_parse_command(item) for item in commands_raw)
    reviewer_app_id = raw.get("reviewer_app_id")
    if isinstance(reviewer_app_id, bool) or not isinstance(reviewer_app_id, int):
        raise AttestationError("reviewer_app_id must be an integer")
    conclusion = _require_str(raw, "conclusion")
    if conclusion not in _ALLOWED_CONCLUSIONS:
        raise AttestationError("unknown attestation conclusion")
    check_name = _require_str(raw, "check_name")
    if "hermes" in check_name.lower():
        raise AttestationError("hermes check names are forbidden")
    return RunAttestation(
        schema_version=schema_version,
        run_id=_require_str(raw, "run_id"),
        head_sha=_require_str(raw, "head_sha"),
        base_sha=_require_str(raw, "base_sha"),
        check_name=check_name,
        reviewer_app_id=reviewer_app_id,
        conclusion=conclusion,
        policy_source=_require_str(raw, "policy_source"),
        commands=commands,
        risk=_require_str(raw, "risk"),
        signature=signature,
    )


def verify_attestation(attestation: RunAttestation, *, hmac_key: bytes) -> None:
    parse_attestation(_attestation_payload(attestation), hmac_key=hmac_key)


def evaluate_merge_policy(
    evidence: MergeEvidence, *, attestation_key: bytes
) -> MergeDecision:
    if evidence.base_branch == evidence.protected_branch:
        return _refuse("never auto-merge the protected default branch")
    if evidence.base_branch != evidence.integration_branch:
        return _refuse("auto-merge is allowed onto the integration branch only")
    if evidence.freeze:
        return _refuse("autonomy freeze refuses merge")
    if not evidence.ruleset_strict:
        return _refuse("strict required status checks are required")
    if evidence.policy_source != POLICY_SOURCE_BASE:
        return _refuse("trusted policy must be loaded from base")
    for check in evidence.checks:
        if "hermes" in check.name.lower():
            return _refuse("hermes check names are forbidden")
    named = [check for check in evidence.checks if check.name == KRONOS_REVIEW_CHECK_NAME]
    if not named:
        if evidence.comments:
            return _refuse("comment is not merge identity")
        if evidence.labels:
            return _refuse("label is not merge identity")
        return _refuse("reviewer check identity is missing")
    for check in named:
        spoofed = _check_identity_failure(check, evidence)
        if spoofed is not None:
            return spoofed
    if not evidence.commands_rerun_in_fresh_sandbox:
        return _refuse("required commands must rerun in a fresh sandbox")
    if evidence.attestation is None:
        return _refuse("signed attestation is required")
    try:
        verify_attestation(evidence.attestation, hmac_key=attestation_key)
    except AttestationError as error:
        return _refuse(str(error))
    attestation = evidence.attestation
    if attestation.head_sha != evidence.pr_head_sha:
        return _refuse("stale sha: attestation is not on the exact PR head")
    if attestation.reviewer_app_id != evidence.expected_reviewer_app_id:
        return _refuse("attestation reviewer integration_id mismatch")
    if attestation.check_name != KRONOS_REVIEW_CHECK_NAME:
        return _refuse("attestation check name mismatch")
    if attestation.policy_source != POLICY_SOURCE_BASE:
        return _refuse("trusted policy must be loaded from base")
    if attestation.conclusion != "success":
        return _refuse("attestation conclusion is not success")
    passed = {
        command.argv
        for command in attestation.commands
        if command.exit_code == 0 and command.sandbox_fresh
    }
    if any(not command.sandbox_fresh for command in attestation.commands):
        return _refuse("required commands must rerun in a fresh sandbox")
    for required in evidence.required_commands:
        if required not in passed:
            return _refuse("required commands must rerun in a fresh sandbox")
    if not evidence.review_threads_resolved:
        return _refuse("review threads must be resolved")
    return MergeDecision(
        allowed=True,
        reason="reviewer identity satisfied",
        target="integration",
    )


def _check_identity_failure(
    check: CheckRunIdentity, evidence: MergeEvidence
) -> MergeDecision | None:
    if check.posted_by == POSTED_BY_WORKER:
        return _refuse("worker token cannot publish reviewer identity")
    if check.posted_by == POSTED_BY_CONTROLLER:
        return _refuse("controller cannot publish the reviewer check")
    if check.posted_by == POSTED_BY_FOREIGN:
        return _refuse("foreign App cannot satisfy reviewer integration_id")
    if check.app_id is None:
        return _refuse("integration_id is required on the reviewer check")
    if check.app_id != evidence.expected_reviewer_app_id:
        return _refuse("foreign App cannot satisfy reviewer integration_id")
    if check.posted_by != POSTED_BY_REVIEWER:
        return _refuse("reviewer identity mismatch")
    if check.head_sha != evidence.pr_head_sha:
        return _refuse("stale sha: check is not on the exact PR head")
    if check.conclusion != "success":
        return _refuse("reviewer check conclusion is not success")
    return None


def _refuse(reason: str) -> MergeDecision:
    return MergeDecision(allowed=False, reason=reason, target="")


def _attestation_payload(attestation: RunAttestation) -> dict[str, object]:
    return {
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
                "argv": list(command.argv),
                "exit_code": command.exit_code,
                "sandbox_fresh": command.sandbox_fresh,
            }
            for command in attestation.commands
        ],
        "risk": attestation.risk,
        "signature": attestation.signature,
    }


def _parse_command(raw: object) -> CommandOutcome:
    if not isinstance(raw, Mapping):
        raise AttestationError("command must be a mapping")
    argv = raw.get("argv")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise AttestationError("command argv must be a list of strings")
    exit_code = raw.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise AttestationError("command exit_code must be an integer")
    sandbox_fresh = raw.get("sandbox_fresh")
    if not isinstance(sandbox_fresh, bool):
        raise AttestationError("command sandbox_fresh must be a boolean")
    return CommandOutcome(argv=tuple(argv), exit_code=exit_code, sandbox_fresh=sandbox_fresh)


def _require_str(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise AttestationError(f"{key} must be a non-empty string")
    return value


def required_commands_from_policy(commands: Sequence[Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(item) for item in commands)
