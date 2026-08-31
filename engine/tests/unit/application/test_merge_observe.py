# SPDX-License-Identifier: AGPL-3.0-or-later
"""MergeService loads live GitHub evidence and never trusts caller-supplied flags."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping

import pytest
from tests.support.github_fixture import controller_stack

from kronos_engine.application.merge import MergeRefused, MergeService
from kronos_engine.domain.attestations import ATTESTATION_SCHEMA_VERSION
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.ports.forge import DefaultBranchWriteRefused

HEAD_SHA = "c" * 40
MOVED_SHA = "e" * 40
ATTESTATION_KEY = b"kronos-test-attestation-key"
REVIEWER_APP_ID = 1002
CONTROLLER_APP_ID = 1001

POLICY_YAML = """schema_version: 2
branches:
  integration: integration
  protected: main
commands:
  setup: []
  test:
    - pytest
    - -q
  lint: []
  build: []
autonomy:
  freeze: false
  invent_issues: false
  refill_enabled: false
paths:
  locked_prefixes: []
risk:
  floor: high
budgets:
  max_attempts_per_issue: 3
  max_dispatches_per_day: 12
  breaker_failure_limit: 4
  dry_run_meters: false
wip:
  ready: 2
  running: 3
executor:
  profile: standard
  sandbox: default
indexing:
  enabled: true
  exclude_prefixes:
    - node_modules/
  max_file_bytes: 1048576
"""


def _sign(payload: Mapping[str, object]) -> str:
    body = {key: value for key, value in payload.items() if key != "signature"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(ATTESTATION_KEY, canonical, hashlib.sha256).hexdigest()


def _attestation_json(*, head_sha: str, base_sha: str) -> str:
    payload: dict[str, object] = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "run_id": "run-observe",
        "head_sha": head_sha,
        "base_sha": base_sha,
        "check_name": KRONOS_REVIEW_CHECK_NAME,
        "reviewer_app_id": REVIEWER_APP_ID,
        "conclusion": "success",
        "policy_source": "base",
        "commands": [{"argv": ["pytest", "-q"], "exit_code": 0, "sandbox_fresh": True}],
        "risk": "high",
    }
    payload["signature"] = _sign(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _service(forge: object) -> MergeService:
    return MergeService(
        forge,  # type: ignore[arg-type]
        attestation_key=ATTESTATION_KEY,
        expected_reviewer_app_id=REVIEWER_APP_ID,
        expected_controller_app_id=CONTROLLER_APP_ID,
    )


def _seed_eligible(fixture: object, *, head_sha: str = HEAD_SHA, base: str = "integration"):
    pull = fixture.seed_pull(  # type: ignore[union-attr]
        head="kronos/observe",
        base=base,
        head_sha=head_sha,
        base_sha=fixture.integration_sha,  # type: ignore[union-attr]
    )
    fixture.seed_contents(  # type: ignore[union-attr]
        fixture.integration_sha,  # type: ignore[union-attr]
        ".kronos/config.yaml",
        POLICY_YAML,
    )
    fixture.seed_check_run(  # type: ignore[union-attr]
        name=KRONOS_REVIEW_CHECK_NAME,
        head_sha=head_sha,
        app_id=REVIEWER_APP_ID,
        output={
            "title": KRONOS_REVIEW_CHECK_NAME,
            "summary": "independent review passed",
            "text": _attestation_json(head_sha=head_sha, base_sha=fixture.integration_sha),  # type: ignore[union-attr]
        },
    )
    fixture.seed_ruleset(  # type: ignore[union-attr]
        {
            "name": "kronos-integration",
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [
                            {
                                "context": KRONOS_REVIEW_CHECK_NAME,
                                "integration_id": REVIEWER_APP_ID,
                            }
                        ],
                    },
                }
            ],
        }
    )
    return pull


def test_merge_service_gets_live_github_evidence_and_merges_integration() -> None:
    forge, fixture, _auth = controller_stack()
    pull = _seed_eligible(fixture)
    decision = _service(forge).merge_if_eligible(pull["number"])
    assert decision.allowed is True
    assert fixture.merge_calls() == (pull["number"],)
    logs = " ".join(fixture.captured_logs())
    assert f"GET /repos/acme/app/pulls/{pull['number']}" in logs
    assert f"GET /repos/acme/app/commits/{HEAD_SHA}/check-runs" in logs
    assert "GET /repos/acme/app/rulesets" in logs
    assert any("reviewThreads" in query for query in fixture.graphql_queries())
    assert "posted_by" not in fixture.check_runs()[0]


def test_merge_service_refuses_third_branch_pr() -> None:
    forge, fixture, _auth = controller_stack()
    pull = _seed_eligible(fixture, base="release")
    with pytest.raises((MergeRefused, DefaultBranchWriteRefused), match="integration"):
        _service(forge).merge_if_eligible(pull["number"])
    assert fixture.merge_calls() == ()


def test_merge_service_refuses_when_head_moved_after_review() -> None:
    forge, fixture, _auth = controller_stack()
    pull = _seed_eligible(fixture, head_sha=HEAD_SHA)
    fixture.move_pull_head(pull["number"], MOVED_SHA)
    with pytest.raises(MergeRefused):
        _service(forge).merge_if_eligible(pull["number"])
    assert fixture.merge_calls() == ()
