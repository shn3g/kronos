# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer auth uses the reviewer App only. No GH_TOKEN fallback."""

from __future__ import annotations

import pytest
from tests.support import MemorySecrets, RecordingTransport, rsa_pem

from kronos_engine.domain.github import REVIEWER_PRIVATE_KEY_REF
from kronos_engine.ports.forge import AppCredentials, ForgeAuthError
from kronos_reviewer.auth import ReviewerAuth, ReviewerAuthError


def _auth(secrets: MemorySecrets, transport: RecordingTransport) -> ReviewerAuth:
    return ReviewerAuth(
        secrets=secrets,
        credentials=AppCredentials(app_id=1002, installation_id=2002, role="reviewer"),
        transport=transport,
    )


def test_missing_reviewer_key_does_not_fall_back_to_gh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_should_never_be_used")
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_also_forbidden")
    transport = RecordingTransport()
    auth = _auth(MemorySecrets(), transport)
    with pytest.raises((ReviewerAuthError, ForgeAuthError), match="reviewer"):
        auth.mint()
    assert transport.requests == []


def test_reviewer_mint_uses_app_installation_token_not_gh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_spoof")
    secrets = MemorySecrets()
    secrets.put(REVIEWER_PRIVATE_KEY_REF, rsa_pem())
    transport = RecordingTransport()
    token = _auth(secrets, transport).mint()
    assert token.require_fresh() == "ghs_fixture_reviewer"
    assert "ghp_spoof" not in token.require_fresh()
    authz = transport.requests[0].headers.get("Authorization") or ""
    assert authz.startswith("Bearer ")
    assert "ghp_spoof" not in authz


def test_reviewer_auth_refuses_controller_role() -> None:
    secrets = MemorySecrets()
    secrets.put(REVIEWER_PRIVATE_KEY_REF, rsa_pem())
    auth = ReviewerAuth(
        secrets=secrets,
        credentials=AppCredentials(app_id=1001, installation_id=2001, role="controller"),
        transport=RecordingTransport(),
    )
    with pytest.raises(ReviewerAuthError, match="reviewer"):
        auth.mint()
