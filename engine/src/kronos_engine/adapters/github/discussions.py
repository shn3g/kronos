# SPDX-License-Identifier: AGPL-3.0-or-later
"""Idempotent GitHub Discussions via GraphQL."""

from __future__ import annotations

from kronos_engine.adapters.github.client import GitHubClient, marker_in
from kronos_engine.ports.forge import (
    DiscussionRef,
    ForgeTarget,
    IdempotencyKey,
    provenance_marker,
)

_LIST_QUERY = """
query($owner: String!, $repo: String!) {
  repository(owner: $owner, name: $repo) {
    discussions(first: 100) {
      nodes { number body url }
    }
  }
}
"""

_CREATE_MUTATION = """
mutation($owner: String!, $repo: String!, $title: String!, $body: String!) {
  createDiscussion(input: {
    repositoryId: $owner,
    title: $title,
    body: $body,
    categoryId: "general"
  }) {
    discussion { number url body }
  }
}
"""


def create_discussion(
    client: GitHubClient,
    target: ForgeTarget,
    title: str,
    body: str,
    key: IdempotencyKey,
) -> DiscussionRef:
    listed = client.request_json(
        "POST",
        "/graphql",
        json_body={
            "query": _LIST_QUERY,
            "variables": {"owner": target.owner, "repo": target.repo},
        },
    )
    for node in _discussion_nodes(listed):
        if marker_in(str(node.get("body") or ""), key):
            return DiscussionRef(
                number=_as_int(node.get("number")),
                url=str(node.get("url") or ""),
                created=False,
            )
    created = client.request_json(
        "POST",
        "/graphql",
        json_body={
            "query": _CREATE_MUTATION,
            "variables": {
                "owner": target.owner,
                "repo": target.repo,
                "title": title,
                "body": f"{body}\n\n{provenance_marker(key)}",
            },
        },
    )
    discussion = _created_discussion(created)
    return DiscussionRef(
        number=_as_int(discussion.get("number")),
        url=str(discussion.get("url") or ""),
        created=True,
    )


def _discussion_nodes(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    repository = data.get("repository")
    if not isinstance(repository, dict):
        return []
    discussions = repository.get("discussions")
    if not isinstance(discussions, dict):
        return []
    nodes = discussions.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [item for item in nodes if isinstance(item, dict)]


def _created_discussion(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}
    wrapper = data.get("createDiscussion")
    if not isinstance(wrapper, dict):
        return {}
    discussion = wrapper.get("discussion")
    return discussion if isinstance(discussion, dict) else {}


def _as_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError("expected int")
