# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer publishes one App-bound check and cannot push or merge."""

from __future__ import annotations

import json

import pytest
from tests.support import HEAD_SHA, REVIEWER_APP_ID, RecordingTransport

from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_reviewer.check_run import (
    ReviewerCannotMerge,
    ReviewerCannotPush,
    ReviewerCheckClient,
    ReviewerCheckRefused,
)


def test_posts_expected_check_name_on_exact_head_sha() -> None:
    transport = RecordingTransport()
    client = ReviewerCheckClient(transport=transport, app_id=REVIEWER_APP_ID)
    posted = client.post_success(head_sha=HEAD_SHA, summary="ok", token="ghs_fixture_reviewer")
    request = next(item for item in transport.requests if item.url.endswith("/check-runs"))
    payload = json.loads(request.body.decode() if request.body else "{}")
    assert payload["name"] == KRONOS_REVIEW_CHECK_NAME
    assert payload["head_sha"] == HEAD_SHA
    assert payload["conclusion"] == "success"
    assert posted["app"]["id"] == REVIEWER_APP_ID
    assert "hermes" not in payload["name"].lower()
    assert request.headers.get("Authorization") == "Bearer ghs_fixture_reviewer"


def test_refuses_success_when_verification_failed() -> None:
    client = ReviewerCheckClient(transport=RecordingTransport(), app_id=REVIEWER_APP_ID)
    with pytest.raises(ReviewerCheckRefused):
        client.post_success(head_sha=HEAD_SHA, summary="ok", verified=False)


def test_reviewer_cannot_push_or_merge() -> None:
    client = ReviewerCheckClient(transport=RecordingTransport(), app_id=REVIEWER_APP_ID)
    with pytest.raises(ReviewerCannotPush, match="push"):
        client.push("integration", HEAD_SHA)
    with pytest.raises(ReviewerCannotMerge, match="merge"):
        client.merge_pull(12)
