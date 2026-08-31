# SPDX-License-Identifier: AGPL-3.0-or-later
"""Publish the App-bound reviewer check. Push and merge are impossible here."""

from __future__ import annotations

import json

from kronos_engine.domain.attestations import RunAttestation, attestation_payload
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME

from kronos_reviewer.http import DEFAULT_TIMEOUT_SECONDS, HttpRequest, HttpTransport


class ReviewerCannotPush(RuntimeError):
    """The reviewer App cannot push refs."""


class ReviewerCannotMerge(RuntimeError):
    """The reviewer App cannot merge pull requests."""


class ReviewerCheckRefused(RuntimeError):
    """Success checks are published only after independent verification."""


class ReviewerCheckClient:
    def __init__(
        self,
        transport: HttpTransport,
        app_id: int,
        *,
        owner: str,
        repo: str,
        base_url: str = "https://api.github.com",
    ) -> None:
        if not owner or not repo:
            raise ReviewerCheckRefused("owner and repo are required")
        self._transport = transport
        self.app_id = app_id
        self._owner = owner
        self._repo = repo
        self._base_url = base_url.rstrip("/")

    def post_success(
        self,
        *,
        head_sha: str,
        summary: str,
        verified: bool = True,
        token: str | None = None,
        attestation: RunAttestation | None = None,
    ) -> dict[str, object]:
        if not verified:
            raise ReviewerCheckRefused("refusing to publish success without verification")
        if "hermes" in KRONOS_REVIEW_CHECK_NAME.lower():
            raise ReviewerCheckRefused("hermes check names are forbidden")
        if not token:
            raise ReviewerCheckRefused("reviewer App token is required to publish the check")
        output: dict[str, object] = {"title": KRONOS_REVIEW_CHECK_NAME, "summary": summary}
        if attestation is not None:
            output["text"] = json.dumps(
                attestation_payload(attestation), sort_keys=True, separators=(",", ":")
            )
        payload = {
            "name": KRONOS_REVIEW_CHECK_NAME,
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": "success",
            "output": output,
        }
        response = self._transport.send(
            HttpRequest(
                method="POST",
                url=f"{self._base_url}/repos/{self._owner}/{self._repo}/check-runs",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                body=json.dumps(payload).encode(),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        )
        if response.status < 200 or response.status >= 300:
            raise ReviewerCheckRefused(f"check-run POST failed: {response.status}")
        body = json.loads(response.body.decode() or "{}")
        if not isinstance(body, dict):
            raise ReviewerCheckRefused("check-run response was not an object")
        return body

    def push(self, ref: str, sha: str) -> None:
        _ = ref
        _ = sha
        raise ReviewerCannotPush("reviewer cannot push")

    def merge_pull(self, number: int) -> None:
        _ = number
        raise ReviewerCannotMerge("reviewer cannot merge")
