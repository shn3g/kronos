# SPDX-License-Identifier: AGPL-3.0-or-later
"""Feature branches from the integration head. Never write the protected default."""

from __future__ import annotations

from kronos_engine.adapters.github.client import GitHubClient
from kronos_engine.ports.forge import (
    BranchRef,
    DefaultBranchWriteRefused,
    ForgeTarget,
    IdempotencyKey,
)


def create_feature_branch(
    client: GitHubClient,
    target: ForgeTarget,
    name: str,
    key: IdempotencyKey,
) -> BranchRef:
    _ = key
    if name == target.protected_branch:
        raise DefaultBranchWriteRefused("refusing write to the protected default branch")
    ref_path = f"/repos/{target.owner}/{target.repo}/git/ref/heads/{name}"
    existing = _safe_ref(client, ref_path)
    if existing is not None:
        return BranchRef(name=name, sha=existing, created=False)
    head = _safe_ref(
        client,
        f"/repos/{target.owner}/{target.repo}/git/ref/heads/{target.integration_branch}",
    )
    if head is None:
        raise DefaultBranchWriteRefused("integration head is missing")
    client.request_json(
        "POST",
        f"/repos/{target.owner}/{target.repo}/git/refs",
        json_body={"ref": f"refs/heads/{name}", "sha": head},
    )
    return BranchRef(name=name, sha=head, created=True)


def _safe_ref(client: GitHubClient, path: str) -> str | None:
    try:
        payload = client.request_json("GET", path)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    obj = payload.get("object")
    if isinstance(obj, dict):
        nested = obj.get("sha")
        if isinstance(nested, str):
            return nested
    sha = payload.get("sha")
    return sha if isinstance(sha, str) else None
