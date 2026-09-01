# SPDX-License-Identifier: AGPL-3.0-or-later
"""Idempotent GitHub issues, comments, and labels."""

from __future__ import annotations

from collections.abc import Sequence

from kronos_engine.adapters.github.client import GitHubClient, marker_in
from kronos_engine.ports.forge import (
    CommentRef,
    ForgeTarget,
    ForgeTransientError,
    IdempotencyKey,
    IssueRef,
    LabelChange,
    provenance_marker,
)

_LABEL_COLOR = "ededed"


def ensure_labels(
    client: GitHubClient,
    target: ForgeTarget,
    labels: Sequence[str],
) -> None:
    path = f"/repos/{target.owner}/{target.repo}/labels"
    for name in labels:
        try:
            client.request_json(
                "POST",
                path,
                json_body={"name": name, "color": _LABEL_COLOR},
            )
        except ForgeTransientError as error:
            if "422" not in str(error):
                raise


def create_issue(
    client: GitHubClient,
    target: ForgeTarget,
    title: str,
    body: str,
    labels: Sequence[str],
    key: IdempotencyKey,
) -> IssueRef:
    path = f"/repos/{target.owner}/{target.repo}/issues"
    for raw in client.paginate(path, params={"state": "all"}):
        if not isinstance(raw, dict):
            continue
        if marker_in(str(raw.get("body") or ""), key):
            return IssueRef(
                number=int(raw["number"]),
                url=str(raw.get("html_url") or ""),
                created=False,
            )
    ensure_labels(client, target, labels)
    payload = client.request_json(
        "POST",
        path,
        json_body={
            "title": title,
            "body": f"{body}\n\n{provenance_marker(key)}",
            "labels": list(labels),
        },
    )
    assert isinstance(payload, dict)
    return IssueRef(
        number=int(payload["number"]),
        url=str(payload.get("html_url") or ""),
        created=True,
    )


def list_issues(client: GitHubClient, target: ForgeTarget) -> tuple[IssueRef, ...]:
    path = f"/repos/{target.owner}/{target.repo}/issues"
    found: list[IssueRef] = []
    for raw in client.paginate(path, params={"state": "all"}):
        if not isinstance(raw, dict):
            continue
        found.append(
            IssueRef(
                number=int(raw["number"]),
                url=str(raw.get("html_url") or ""),
                created=False,
            )
        )
    return tuple(found)


def add_issue_comment(
    client: GitHubClient,
    target: ForgeTarget,
    issue_number: int,
    body: str,
    key: IdempotencyKey,
) -> CommentRef:
    path = f"/repos/{target.owner}/{target.repo}/issues/{issue_number}/comments"
    for raw in client.paginate(path):
        if not isinstance(raw, dict):
            continue
        if marker_in(str(raw.get("body") or ""), key):
            return CommentRef(id=int(raw["id"]), created=False)
    payload = client.request_json(
        "POST",
        path,
        json_body={"body": f"{body}\n\n{provenance_marker(key)}"},
    )
    assert isinstance(payload, dict)
    return CommentRef(id=int(payload["id"]), created=True)


def add_labels(
    client: GitHubClient,
    target: ForgeTarget,
    issue_number: int,
    labels: Sequence[str],
    key: IdempotencyKey,
) -> LabelChange:
    _ = key
    path = f"/repos/{target.owner}/{target.repo}/issues/{issue_number}/labels"
    existing_raw = client.request_json("GET", path)
    existing: set[str] = set()
    if isinstance(existing_raw, list):
        for item in existing_raw:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                existing.add(item["name"])
            elif isinstance(item, str):
                existing.add(item)
    wanted = set(labels)
    if wanted <= existing:
        return LabelChange(created=False)
    client.request_json("POST", path, json_body={"labels": list(labels)})
    return LabelChange(created=True)
