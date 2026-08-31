# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forge adapter contract: idempotent writes, no default-branch mutation, App auth only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.support.github_fixture import controller_stack
from tests.support.secrets import InMemorySecretStore

from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.ports.forge import (
    DefaultBranchWriteRefused,
    ForgeAuthError,
    ForgeRateLimited,
    IdempotencyKey,
    OperatorConfirmationRequired,
    RequiredCheck,
    RulesetWouldWeaken,
)

TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "github"


def test_reviewer_check_name_is_bound_and_is_not_hermes() -> None:
    assert KRONOS_REVIEW_CHECK_NAME == "kronos-review (kronos-reviewer)"
    assert "hermes" not in KRONOS_REVIEW_CHECK_NAME.lower()
    assert "security-review (hermes-reviewer)" not in KRONOS_REVIEW_CHECK_NAME
    workflow = (TEMPLATES / "kronos-pr.yml").read_text(encoding="utf-8")
    controller = (TEMPLATES / "controller-app-manifest.json").read_text(encoding="utf-8")
    reviewer = (TEMPLATES / "reviewer-app-manifest.json").read_text(encoding="utf-8")
    assert KRONOS_REVIEW_CHECK_NAME in workflow
    assert KRONOS_REVIEW_CHECK_NAME in reviewer
    assert "hermes" not in workflow.lower()
    assert "hermes" not in controller.lower()
    assert "hermes" not in reviewer.lower()
    assert "GH_TOKEN" not in reviewer
    assert "GITHUB_TOKEN" not in reviewer
    reviewer_manifest = json.loads(reviewer)
    assert reviewer_manifest["default_permissions"]["checks"] == "write"
    assert reviewer_manifest["default_permissions"].get("contents") == "read"
    assert "write" != reviewer_manifest["default_permissions"].get("contents")
    controller_manifest = json.loads(controller)
    assert controller_manifest["hook_attributes"]["active"] is False
    assert reviewer_manifest["hook_attributes"]["active"] is False


def test_replayed_issue_comment_label_discussion_and_pr_are_idempotent() -> None:
    forge, fixture, _auth = controller_stack()
    issue_key = IdempotencyKey("issue:acme/app:goal-1")
    first = forge.create_issue(
        title="Fix login",
        body="Users cannot sign in.",
        labels=("bug",),
        key=issue_key,
    )
    second = forge.create_issue(
        title="Fix login",
        body="Users cannot sign in.",
        labels=("bug",),
        key=issue_key,
    )
    assert first.number == second.number
    assert first.created is True
    assert second.created is False
    assert fixture.count_issues() == 1

    comment_key = IdempotencyKey("comment:acme/app:1:intake")
    c1 = forge.add_issue_comment(first.number, "Intake notes.", comment_key)
    c2 = forge.add_issue_comment(first.number, "Intake notes.", comment_key)
    assert c1.id == c2.id
    assert c2.created is False
    assert fixture.count_comments() == 1

    label_key = IdempotencyKey("labels:acme/app:1:intake-ready")
    l1 = forge.add_labels(first.number, ("intake-ready",), label_key)
    l2 = forge.add_labels(first.number, ("intake-ready",), label_key)
    assert l1.created is True
    assert l2.created is False
    assert fixture.issue_labels(first.number) == ("bug", "intake-ready")

    disc_key = IdempotencyKey("discussion:acme/app:design-1")
    d1 = forge.create_discussion("Design", "Notes", disc_key)
    d2 = forge.create_discussion("Design", "Notes", disc_key)
    assert d1.number == d2.number
    assert d2.created is False
    assert fixture.count_discussions() == 1

    branch_key = IdempotencyKey("branch:acme/app:goal-1")
    b1 = forge.create_feature_branch("kronos/goal-1", branch_key)
    b2 = forge.create_feature_branch("kronos/goal-1", branch_key)
    assert b1.name == b2.name == "kronos/goal-1"
    assert b1.sha == fixture.integration_sha
    assert b2.created is False
    assert fixture.branch_created_from("kronos/goal-1") == "integration"

    pr_key = IdempotencyKey("pr:acme/app:goal-1")
    p1 = forge.open_draft_pr(
        title="Fix login",
        body="Fixes #1",
        head="kronos/goal-1",
        key=pr_key,
    )
    p2 = forge.open_draft_pr(
        title="Fix login",
        body="Fixes #1",
        head="kronos/goal-1",
        key=pr_key,
    )
    assert p1.number == p2.number
    assert p1.draft is True
    assert p1.base == "integration"
    assert p2.created is False
    assert fixture.count_pulls() == 1
    assert fixture.logical_action_kinds() == (
        "create_issue",
        "add_issue_comment",
        "add_labels",
        "create_discussion",
        "create_feature_branch",
        "open_draft_pr",
    )


def test_feature_branch_and_draft_pr_never_write_protected_default() -> None:
    forge, fixture, _auth = controller_stack()
    with pytest.raises(DefaultBranchWriteRefused):
        forge.create_feature_branch("main", IdempotencyKey("branch:default"))
    with pytest.raises(DefaultBranchWriteRefused):
        forge.open_draft_pr(
            title="nope",
            body="nope",
            head="main",
            key=IdempotencyKey("pr:onto-default"),
            base="main",
        )
    forge.create_feature_branch("kronos/ok", IdempotencyKey("branch:ok"))
    forge.open_draft_pr(
        title="ok",
        body="ok",
        head="kronos/ok",
        key=IdempotencyKey("pr:ok"),
    )
    assert "main" not in fixture.ref_writes()
    assert fixture.pulls()[0]["base"]["ref"] == "integration"


def test_ruleset_requires_integration_id_and_strict_and_refuses_weaken() -> None:
    forge, fixture, _auth = controller_stack()
    proposal = forge.propose_ruleset(reviewer_integration_id=1002)
    assert proposal.strict is True
    assert proposal.bypass_actors == ()
    assert any(
        check.context == KRONOS_REVIEW_CHECK_NAME and check.integration_id == 1002
        for check in proposal.required_checks
    )
    with pytest.raises(OperatorConfirmationRequired):
        forge.apply_ruleset(proposal, confirm=False)

    fixture.seed_ruleset(
        {
            "name": "kronos-integration",
            "bypass_actors": [{"actor_id": 9, "actor_type": "Integration"}],
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": False,
                        "required_status_checks": [
                            {"context": "Frontend", "integration_id": 55},
                        ],
                    },
                }
            ],
        }
    )
    unioned = forge.propose_ruleset(reviewer_integration_id=1002)
    contexts = {check.context: check.integration_id for check in unioned.required_checks}
    assert contexts["Frontend"] == 55
    assert contexts[KRONOS_REVIEW_CHECK_NAME] == 1002
    assert unioned.strict is True
    assert unioned.bypass_actors == ()

    dropped = unioned.replace_required_checks(
        tuple(
            check for check in unioned.required_checks if check.context != "Frontend"
        )
    )
    with pytest.raises(RulesetWouldWeaken, match="check"):
        forge.apply_ruleset(dropped, confirm=True)
    with pytest.raises(RulesetWouldWeaken, match="strict"):
        forge.apply_ruleset(unioned.replace_strict(False), confirm=True)
    with pytest.raises(RulesetWouldWeaken, match="bypass"):
        forge.apply_ruleset(unioned.replace_bypass_actors(({"actor_id": 1},)), confirm=True)
    with pytest.raises(RulesetWouldWeaken, match="integration_id"):
        forge.apply_ruleset(unioned.drop_integration_ids(), confirm=True)

    applied = forge.apply_ruleset(unioned, confirm=True)
    assert applied.strict is True
    replayed = forge.apply_ruleset(unioned, confirm=True)
    assert replayed.id == applied.id
    assert fixture.count_ruleset_puts() == 1


def test_installation_tokens_come_from_app_keys_not_gh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_should_never_be_used")
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_also_forbidden")
    forge, fixture, auth = controller_stack()
    token = auth.mint("controller")
    assert token.require_fresh().startswith("ghs_")
    assert "ghp_should_never_be_used" not in token.require_fresh()
    assert "ghs_also_forbidden" not in token.require_fresh()
    assert fixture.last_token_request_role() == "controller"
    forge.create_issue("auth", "body", (), IdempotencyKey("issue:auth"))
    headers = fixture.last_mutating_headers()
    assert headers["Authorization"].startswith("Bearer ghs_")
    assert "ghp_should_never_be_used" not in headers["Authorization"]
    assert "ghs_also_forbidden" not in str(fixture.captured_logs())

    empty = InMemorySecretStore()
    _missing_forge, _missing_fixture, auth_missing = controller_stack(secrets=empty)
    with pytest.raises(ForgeAuthError, match="private key"):
        auth_missing.mint("controller")


def test_reviewer_auth_does_not_fall_back_to_gh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_reviewer_spoof")
    secrets = InMemorySecretStore()
    from tests.support.github_fixture import TEST_CONTROLLER_PEM

    secrets.put("github:controller:private_key", TEST_CONTROLLER_PEM)
    _forge, _fixture, auth = controller_stack(secrets=secrets)
    with pytest.raises(ForgeAuthError, match="reviewer"):
        auth.mint("reviewer")


def test_pagination_etags_timeouts_and_backoff() -> None:
    forge, fixture, _auth = controller_stack()
    fixture.seed_issues(30)
    listed = forge.list_issues()
    assert len(listed) == 30
    assert fixture.page_fetches() >= 2

    fixture.enable_etags()
    forge.list_issues()
    conditional = fixture.last_request()
    assert "If-None-Match" in conditional.headers
    forge.list_issues()
    assert fixture.last_status() == 304

    fixture.queue_status(429)
    forge.create_issue("retry", "body", (), IdempotencyKey("issue:retry"))
    assert fixture.retried_after_status(429) is True

    fixture.queue_status(500)
    forge.create_issue("retry5xx", "body", (), IdempotencyKey("issue:retry5xx"))
    assert fixture.retried_after_status(500) is True

    fixture.queue_status(403, remaining=0)
    forge.create_issue("retry403", "body", (), IdempotencyKey("issue:retry403"))
    assert fixture.retried_after_status(403) is True

    fixture.always_status(429)
    with pytest.raises(ForgeRateLimited):
        forge.create_issue("give-up", "body", (), IdempotencyKey("issue:give-up"))
    assert fixture.client_timeout_seconds() > 0


def test_webhook_ingress_is_off_unless_configured() -> None:
    _forge, fixture, _auth = controller_stack()
    assert fixture.webhook_enabled is False
    from tests.support.secrets import InMemorySecretStore

    from kronos_engine.application.github_setup import GitHubSetupService
    from kronos_engine.state.github_apps import MemoryGithubAppStore

    setup = GitHubSetupService(
        apps=MemoryGithubAppStore(),
        secrets=InMemorySecretStore(),
        transport=fixture,
    )
    status = setup.status()
    assert status.webhook_enabled is False
    assert status.poll_mode == "conditional"


def test_controller_does_not_post_reviewer_check() -> None:
    forge, fixture, _auth = controller_stack()
    from kronos_engine.adapters.github.checks import ControllerCannotPostReviewCheck

    with pytest.raises(ControllerCannotPostReviewCheck):
        forge.post_check_run(
            head_sha=fixture.integration_sha,
            name=KRONOS_REVIEW_CHECK_NAME,
            conclusion="success",
        )
    assert fixture.check_runs() == []


class _FakeClock:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def test_apply_posts_kronos_ruleset_and_leaves_foreign_ruleset() -> None:
    forge, fixture, _auth = controller_stack()
    fixture.seed_ruleset(
        {
            "id": 77,
            "name": "protect-default",
            "bypass_actors": [],
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
            ],
        }
    )
    proposal = forge.propose_ruleset(reviewer_integration_id=1002)
    applied = forge.apply_ruleset(proposal, confirm=True)
    foreign = fixture.ruleset_by_id(77)
    assert foreign is not None
    assert foreign["id"] == 77
    assert foreign["name"] == "protect-default"
    assert applied.id != 77
    assert applied.created is True
    kronos = fixture.ruleset_named("kronos-integration")
    assert kronos is not None
    assert kronos["id"] == applied.id
    assert {rule["type"] for rule in foreign["rules"]} == {
        "deletion",
        "non_fast_forward",
        "pull_request",
    }


def test_updating_kronos_ruleset_keeps_non_status_rules() -> None:
    forge, fixture, _auth = controller_stack()
    fixture.seed_ruleset(
        {
            "name": "kronos-integration",
            "bypass_actors": [],
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [
                            {"context": "Frontend", "integration_id": 55},
                        ],
                    },
                },
            ],
        }
    )
    proposal = forge.propose_ruleset(reviewer_integration_id=1002)
    applied = forge.apply_ruleset(proposal, confirm=True)
    kronos = fixture.ruleset_by_id(applied.id)
    assert kronos is not None
    types = [rule["type"] for rule in kronos["rules"]]
    assert types.count("deletion") == 1
    assert "non_fast_forward" in types
    assert "pull_request" in types
    assert "required_status_checks" in types


def test_integration_id_required_only_on_kronos_review_check() -> None:
    forge, fixture, _auth = controller_stack()
    fixture.seed_ruleset(
        {
            "name": "kronos-integration",
            "bypass_actors": [],
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [
                            {"context": "Frontend"},
                            {"context": KRONOS_REVIEW_CHECK_NAME, "integration_id": 1002},
                        ],
                    },
                }
            ],
        }
    )
    proposal = forge.propose_ruleset(reviewer_integration_id=1002)
    contexts = {check.context: check.integration_id for check in proposal.required_checks}
    assert contexts["Frontend"] is None
    assert contexts[KRONOS_REVIEW_CHECK_NAME] == 1002
    applied = forge.apply_ruleset(proposal, confirm=True)
    kronos = fixture.ruleset_by_id(applied.id)
    assert kronos is not None
    frontend = next(
        check
        for rule in kronos["rules"]
        if rule.get("type") == "required_status_checks"
        for check in (rule.get("parameters") or {}).get("required_status_checks") or []
        if check["context"] == "Frontend"
    )
    assert "integration_id" not in frontend
    missing_kronos = proposal.replace_required_checks(
        tuple(
            check
            if check.context != KRONOS_REVIEW_CHECK_NAME
            else RequiredCheck(context=check.context, integration_id=None)
            for check in proposal.required_checks
        )
    )
    with pytest.raises(RulesetWouldWeaken, match="integration_id"):
        forge.apply_ruleset(missing_kronos, confirm=True)


def test_create_discussion_uses_repository_and_category_node_ids() -> None:
    forge, fixture, _auth = controller_stack()
    created = forge.create_discussion(
        "Design", "Notes", IdempotencyKey("discussion:graphql-nodes")
    )
    assert created.created is True
    queries = fixture.graphql_queries()
    assert any("discussionCategories" in query for query in queries)
    variables = fixture.last_create_discussion_variables()
    assert variables["repositoryId"] == fixture.repository_node_id
    assert variables["categoryId"] == fixture.general_category_id
    assert variables["repositoryId"] != "acme"
    assert variables["categoryId"] != "general"


def test_backoff_honors_retry_after_and_403_secondary_limit() -> None:
    clock = _FakeClock()
    forge, fixture, _auth = controller_stack(sleep=clock.sleep, rng=lambda: 0.0)
    fixture.queue_status(403, remaining=8, retry_after=2)
    forge.create_issue("retry-403", "body", (), IdempotencyKey("issue:retry-after-403"))
    assert fixture.retried_after_status(403) is True
    assert clock.sleeps[0] == 2.0

    clock.sleeps.clear()
    fixture.queue_status(429, remaining=None, retry_after=3)
    forge.create_issue("retry-429", "body", (), IdempotencyKey("issue:retry-after-429"))
    assert clock.sleeps[0] == 3.0

    clock.sleeps.clear()
    fixture.queue_status(500)
    forge.create_issue("retry-500", "body", (), IdempotencyKey("issue:exp-500"))
    assert clock.sleeps[0] == 1.0


def test_etag_304_returns_cached_ref_so_replay_does_not_post_branch() -> None:
    forge, fixture, _auth = controller_stack()
    fixture.enable_etags()
    key = IdempotencyKey("branch:etag-replay")
    first = forge.create_feature_branch("kronos/etag", key)
    second = forge.create_feature_branch("kronos/etag", key)
    third = forge.create_feature_branch("kronos/etag", key)
    assert first.created is True
    assert second.created is False
    assert third.created is False
    assert third.sha == first.sha
    assert fixture.logical_action_kinds().count("create_feature_branch") == 1
    assert fixture.last_status() == 304


def test_mint_uses_client_base_url() -> None:
    _forge, fixture, auth = controller_stack(base_url="https://github.fixture.test")
    token = auth.mint("controller")
    assert token.require_fresh().startswith("ghs_")
    assert fixture.last_request().url.startswith(
        "https://github.fixture.test/app/installations/"
    )
