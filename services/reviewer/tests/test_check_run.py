# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer publishes one App-bound check and cannot push or merge."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from tests.support import HEAD_SHA, REVIEWER_APP_ID, RecordingTransport

from kronos_reviewer.check_run import (
    ReviewerCannotMerge,
    ReviewerCannotPush,
    ReviewerCheckClient,
    ReviewerCheckRefused,
)


@dataclass(frozen=True)
class _BareResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def test_posts_expected_check_name_on_exact_head_sha() -> None:
    transport = RecordingTransport()
    client = ReviewerCheckClient(
        transport=transport, app_id=REVIEWER_APP_ID, owner="acme", repo="app"
    )
    posted = client.post_success(head_sha=HEAD_SHA, summary="ok", token="ghs_fixture_reviewer")
    request = next(item for item in transport.requests if item.url.endswith("/check-runs"))
    payload = json.loads(request.body.decode() if request.body else "{}")
    assert payload["name"] == KRONOS_REVIEW_CHECK_NAME
    assert payload["head_sha"] == HEAD_SHA
    assert payload["conclusion"] == "success"
    assert posted["app"]["id"] == REVIEWER_APP_ID
    assert "hermes" not in payload["name"].lower()
    assert request.headers.get("Authorization") == "Bearer ghs_fixture_reviewer"


def test_check_client_requires_owner_and_repo() -> None:
    with pytest.raises(TypeError):
        ReviewerCheckClient(transport=RecordingTransport(), app_id=REVIEWER_APP_ID)


def test_check_client_raises_on_non_2xx() -> None:
    transport = RecordingTransport()
    transport.check_status = 401
    client = ReviewerCheckClient(
        transport=transport, app_id=REVIEWER_APP_ID, owner="acme", repo="app"
    )
    with pytest.raises(ReviewerCheckRefused, match="401"):
        client.post_success(head_sha=HEAD_SHA, summary="ok", token="ghs_fixture_reviewer")


def test_check_client_does_not_invent_app_identity() -> None:
    class BareTransport:
        def send(self, request: object) -> _BareResponse:
            _ = request
            return _BareResponse(201, {}, b'{"id": 9, "name": "kronos-review (kronos-reviewer)"}')

    client = ReviewerCheckClient(
        transport=BareTransport(), app_id=REVIEWER_APP_ID, owner="acme", repo="app"
    )
    posted = client.post_success(head_sha=HEAD_SHA, summary="ok", token="ghs_ok")
    assert "app" not in posted


def test_refuses_success_when_verification_failed() -> None:
    client = ReviewerCheckClient(
        transport=RecordingTransport(), app_id=REVIEWER_APP_ID, owner="acme", repo="app"
    )
    with pytest.raises(ReviewerCheckRefused):
        client.post_success(head_sha=HEAD_SHA, summary="ok", verified=False)


def test_reviewer_cannot_push_or_merge() -> None:
    client = ReviewerCheckClient(
        transport=RecordingTransport(), app_id=REVIEWER_APP_ID, owner="acme", repo="app"
    )
    with pytest.raises(ReviewerCannotPush, match="push"):
        client.push("integration", HEAD_SHA)
    with pytest.raises(ReviewerCannotMerge, match="merge"):
        client.merge_pull(12)
