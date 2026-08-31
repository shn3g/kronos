# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live GitHub reads used by integration merge. Controller App token only."""

from __future__ import annotations

import base64
from collections.abc import Mapping

from kronos_engine.adapters.github.client import GitHubClient
from kronos_engine.adapters.github.pulls import get_pull
from kronos_engine.ports.forge import ForgeTarget, PullRef


def list_check_runs(
    client: GitHubClient, target: ForgeTarget, sha: str
) -> tuple[Mapping[str, object], ...]:
    payload = client.request_json(
        "GET", f"/repos/{target.owner}/{target.repo}/commits/{sha}/check-runs"
    )
    if not isinstance(payload, dict):
        return ()
    runs = payload.get("check_runs")
    if not isinstance(runs, list):
        return ()
    return tuple(item for item in runs if isinstance(item, dict))


def list_issue_comments(
    client: GitHubClient, target: ForgeTarget, number: int
) -> tuple[Mapping[str, object], ...]:
    raw = client.paginate(f"/repos/{target.owner}/{target.repo}/issues/{number}/comments")
    return tuple(item for item in raw if isinstance(item, dict))


def list_issue_labels(client: GitHubClient, target: ForgeTarget, number: int) -> tuple[str, ...]:
    payload = client.request_json(
        "GET", f"/repos/{target.owner}/{target.repo}/issues/{number}/labels"
    )
    if not isinstance(payload, list):
        return ()
    names: list[str] = []
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return tuple(names)


def ruleset_strict(client: GitHubClient, target: ForgeTarget) -> bool:
    listed = client.request_json("GET", f"/repos/{target.owner}/{target.repo}/rulesets")
    if not isinstance(listed, list):
        return False
    for item in listed:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        detail = client.request_json(
            "GET", f"/repos/{target.owner}/{target.repo}/rulesets/{item['id']}"
        )
        if not isinstance(detail, dict):
            continue
        rules = detail.get("rules")
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
                continue
            parameters = rule.get("parameters")
            if isinstance(parameters, dict) and parameters.get(
                "strict_required_status_checks_policy"
            ) is True:
                return True
    return False


def review_threads_resolved(client: GitHubClient, target: ForgeTarget, number: int) -> bool:
    payload = client.request_json(
        "POST",
        "/graphql",
        json_body={
            "query": (
                "query($owner:String!,$name:String!,$number:Int!){"
                "repository(owner:$owner,name:$name){"
                "pullRequest(number:$number){reviewThreads(first:100){nodes{isResolved}}}}}"
            ),
            "variables": {"owner": target.owner, "name": target.repo, "number": number},
        },
    )
    if not isinstance(payload, dict):
        return False
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    repository = data.get("repository")
    if not isinstance(repository, dict):
        return False
    pull = repository.get("pullRequest")
    if not isinstance(pull, dict):
        return False
    threads = pull.get("reviewThreads")
    if not isinstance(threads, dict):
        return False
    nodes = threads.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if isinstance(node, dict) and node.get("isResolved") is False:
            return False
    return True


def file_at_sha(client: GitHubClient, target: ForgeTarget, sha: str, path: str) -> str:
    payload = client.request_json(
        "GET",
        f"/repos/{target.owner}/{target.repo}/contents/{path}",
        params={"ref": sha},
    )
    if not isinstance(payload, dict):
        return ""
    encoding = payload.get("encoding")
    content = payload.get("content")
    if encoding != "base64" or not isinstance(content, str):
        return ""
    return base64.b64decode(content.encode()).decode()


def observed_pull(client: GitHubClient, target: ForgeTarget, number: int) -> PullRef:
    return get_pull(client, target, number)


__all__ = [
    "file_at_sha",
    "list_check_runs",
    "list_issue_comments",
    "list_issue_labels",
    "observed_pull",
    "review_threads_resolved",
    "ruleset_strict",
]
