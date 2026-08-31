# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer process: independent checkout, base policy, sandbox rerun, one check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.support import (
    BASE_SHA,
    HEAD_SHA,
    REVIEWER_APP_ID,
    FakeGit,
    FakeRunner,
    MemorySecrets,
    RecordingTransport,
    policy_mapping,
    rsa_pem,
)

from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME, REVIEWER_PRIVATE_KEY_REF
from kronos_engine.ports.forge import AppCredentials
from kronos_reviewer.auth import ReviewerAuth
from kronos_reviewer.check_run import ReviewerCheckClient
from kronos_reviewer.main import ReviewRequest, review_pull


def test_review_pull_posts_check_after_base_policy_and_fresh_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setenv("GH_TOKEN", "ghp_ignored")
    git = FakeGit()
    git.add_policy(BASE_SHA, policy_mapping(freeze=False, risk="medium", test=("pytest", "-q")))
    git.add_policy(HEAD_SHA, policy_mapping(freeze=False, risk="low", test=()))
    git.add(HEAD_SHA, "README.md", "ok\n")
    git.diffs[(BASE_SHA, HEAD_SHA)] = ("README.md",)
    secrets = MemorySecrets()
    secrets.put(REVIEWER_PRIVATE_KEY_REF, rsa_pem())
    secrets.put("github:reviewer:attestation_key", "kronos-test-attestation-key")
    transport = RecordingTransport()
    outcome = review_pull(
        ReviewRequest(
            pull_number=7,
            head_sha=HEAD_SHA,
            base_sha=BASE_SHA,
            worktree=tmp_path / "wt",
        ),
        git=git,
        runner=FakeRunner(),
        auth=ReviewerAuth(
            secrets=secrets,
            credentials=AppCredentials(
                app_id=REVIEWER_APP_ID, installation_id=2002, role="reviewer"
            ),
            transport=transport,
        ),
        checks=ReviewerCheckClient(transport=transport, app_id=REVIEWER_APP_ID),
        secrets=secrets,
    )
    assert outcome.ok is True
    assert git.reads == [(".kronos/config.yaml", BASE_SHA)]
    check_posts = [item for item in transport.requests if item.url.endswith("/check-runs")]
    assert len(check_posts) == 1
    payload = json.loads(check_posts[0].body.decode())
    assert payload["name"] == KRONOS_REVIEW_CHECK_NAME
    assert payload["head_sha"] == HEAD_SHA
    assert payload["conclusion"] == "success"
    assert check_posts[0].headers.get("Authorization", "").startswith("Bearer ghs_")


def test_review_pull_does_not_succeed_when_head_weakens_untrusted_policy(
    tmp_path: Path,
) -> None:
    git = FakeGit()
    git.add_policy(BASE_SHA, policy_mapping(freeze=False, test=("pytest", "-q")))
    git.add_policy(HEAD_SHA, policy_mapping(freeze=False, test=()))
    git.diffs[(BASE_SHA, HEAD_SHA)] = ("README.md",)
    secrets = MemorySecrets()
    secrets.put(REVIEWER_PRIVATE_KEY_REF, rsa_pem())
    secrets.put("github:reviewer:attestation_key", "kronos-test-attestation-key")
    transport = RecordingTransport()
    runner = FakeRunner(exit_codes={("pytest", "-q"): 1})
    outcome = review_pull(
        ReviewRequest(
            pull_number=8,
            head_sha=HEAD_SHA,
            base_sha=BASE_SHA,
            worktree=tmp_path / "wt",
        ),
        git=git,
        runner=runner,
        auth=ReviewerAuth(
            secrets=secrets,
            credentials=AppCredentials(
                app_id=REVIEWER_APP_ID, installation_id=2002, role="reviewer"
            ),
            transport=transport,
        ),
        checks=ReviewerCheckClient(transport=transport, app_id=REVIEWER_APP_ID),
        secrets=secrets,
    )
    assert outcome.ok is False
    check_posts = [item for item in transport.requests if item.url.endswith("/check-runs")]
    assert check_posts == [] or json.loads(check_posts[0].body.decode())["conclusion"] != "success"
