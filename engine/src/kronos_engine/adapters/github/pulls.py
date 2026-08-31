# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draft PRs that target only the integration branch."""

from __future__ import annotations

from kronos_engine.adapters.github.client import GitHubClient, marker_in
from kronos_engine.ports.forge import (
    DefaultBranchWriteRefused,
    ForgeTarget,
    IdempotencyKey,
    PullRef,
    provenance_marker,
)


def open_draft_pr(
    client: GitHubClient,
    target: ForgeTarget,
    title: str,
    body: str,
    head: str,
    key: IdempotencyKey,
    *,
    base: str | None = None,
) -> PullRef:
    chosen_base = base or target.integration_branch
    if chosen_base != target.integration_branch:
        raise DefaultBranchWriteRefused("draft PRs may target only the integration branch")
    if head == target.protected_branch:
        raise DefaultBranchWriteRefused("refusing a pull from the protected default branch")
    path = f"/repos/{target.owner}/{target.repo}/pulls"
    for raw in client.paginate(path, params={"state": "all"}):
        if not isinstance(raw, dict):
            continue
        if marker_in(str(raw.get("body") or ""), key):
            return _pull_ref(raw, created=False)
    payload = client.request_json(
        "POST",
        path,
        json_body={
            "title": title,
            "body": f"{body}\n\n{provenance_marker(key)}",
            "head": head,
            "base": chosen_base,
            "draft": True,
        },
    )
    assert isinstance(payload, dict)
    return _pull_ref(payload, created=True)


def _pull_ref(raw: dict[str, object], *, created: bool) -> PullRef:
    head = raw.get("head")
    base = raw.get("base")
    head_ref = head["ref"] if isinstance(head, dict) and isinstance(head.get("ref"), str) else ""
    base_ref = base["ref"] if isinstance(base, dict) and isinstance(base.get("ref"), str) else ""
    number = raw.get("number")
    return PullRef(
        number=int(number) if isinstance(number, int) else 0,
        url=str(raw.get("html_url") or ""),
        head=head_ref,
        base=base_ref,
        draft=bool(raw.get("draft", True)),
        created=created,
    )
