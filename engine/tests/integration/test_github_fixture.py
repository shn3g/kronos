# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exit gate: replay every controller command once; no protected default-branch writes."""

from __future__ import annotations

from tests.support.github_fixture import controller_stack

from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.ports.forge import IdempotencyKey


def test_replaying_every_controller_command_is_idempotent_and_skips_default_branch() -> None:
    forge, fixture, _auth = controller_stack()
    commands = (
        lambda: forge.create_issue(
            "Ticket", "Body", ("bug",), IdempotencyKey("issue:replay")
        ),
        lambda: forge.add_issue_comment(1, "Note", IdempotencyKey("comment:replay")),
        lambda: forge.add_labels(1, ("intake-ready",), IdempotencyKey("labels:replay")),
        lambda: forge.create_discussion("Topic", "Body", IdempotencyKey("discussion:replay")),
        lambda: forge.create_feature_branch("kronos/replay", IdempotencyKey("branch:replay")),
        lambda: forge.open_draft_pr(
            "Ticket", "Fixes #1", "kronos/replay", IdempotencyKey("pr:replay")
        ),
        lambda: forge.propose_ruleset(reviewer_integration_id=1002),
        lambda: forge.apply_ruleset(
            forge.propose_ruleset(reviewer_integration_id=1002), confirm=True
        ),
    )
    first_results = [command() for command in commands]
    replayed = [command() for command in commands]
    assert fixture.logical_action_kinds() == (
        "create_issue",
        "add_issue_comment",
        "add_labels",
        "create_discussion",
        "create_feature_branch",
        "open_draft_pr",
        "apply_ruleset",
    )
    assert "main" not in fixture.ref_writes()
    assert fixture.pulls()[0]["base"]["ref"] != "main"
    assert fixture.pulls()[0]["base"]["ref"] == "integration"
    assert fixture.pulls()[0]["draft"] is True
    assert first_results[0].number == replayed[0].number
    assert KRONOS_REVIEW_CHECK_NAME in fixture.applied_ruleset_contexts()
    assert fixture.applied_ruleset_strict() is True
    assert fixture.applied_ruleset_integration_ids() == (1002,)
    assert fixture.applied_ruleset_bypass_actors() == []
    assert fixture.count_issues() == 1
    assert fixture.count_comments() == 1
    assert fixture.count_discussions() == 1
    assert fixture.count_pulls() == 1
    assert fixture.count_ruleset_puts() == 1
