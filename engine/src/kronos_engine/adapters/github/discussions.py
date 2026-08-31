# SPDX-License-Identifier: AGPL-3.0-or-later
"""Idempotent GitHub Discussions via GraphQL."""

from __future__ import annotations

from kronos_engine.adapters.github.client import GitHubClient, marker_in
from kronos_engine.ports.forge import (
    DiscussionRef,
    ForgeTarget,
    ForgeTransientError,
    IdempotencyKey,
    provenance_marker,
)

_REPO_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    id
    discussionCategories(first: 20) {
      nodes { id name }
    }
    discussions(first: 100, after: $after) {
      nodes { number body url }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

_CREATE_MUTATION = """
mutation($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
  createDiscussion(input: {
    repositoryId: $repositoryId,
    title: $title,
    body: $body,
    categoryId: $categoryId
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
    repository_id, category_id, nodes = _load_repository(client, target)
    for node in nodes:
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
                "repositoryId": repository_id,
                "categoryId": category_id,
                "title": title,
                "body": f"{body}\n\n{provenance_marker(key)}",
            },
        },
    )
    if isinstance(created, dict) and created.get("errors"):
        raise ForgeTransientError("GitHub discussion mutation failed")
    discussion = _created_discussion(created)
    return DiscussionRef(
        number=_as_int(discussion.get("number")),
        url=str(discussion.get("url") or ""),
        created=True,
    )


def _load_repository(
    client: GitHubClient, target: ForgeTarget
) -> tuple[str, str, list[dict[str, object]]]:
    nodes: list[dict[str, object]] = []
    after: str | None = None
    repository_id = ""
    category_id = ""
    while True:
        payload = client.request_json(
            "POST",
            "/graphql",
            json_body={
                "query": _REPO_QUERY,
                "variables": {
                    "owner": target.owner,
                    "name": target.repo,
                    "after": after,
                },
            },
        )
        repository = _repository(payload)
        repository_id = str(repository.get("id") or repository_id)
        if not category_id:
            category_id = _category_id(repository)
        nodes.extend(_discussion_nodes_from_repo(repository))
        page = repository.get("discussions")
        info = page.get("pageInfo") if isinstance(page, dict) else None
        if not isinstance(info, dict) or info.get("hasNextPage") is not True:
            break
        cursor = info.get("endCursor")
        if not isinstance(cursor, str) or cursor == after:
            break
        after = cursor
    if not repository_id or not category_id:
        raise ForgeTransientError("GitHub discussion repository or category is missing")
    return repository_id, category_id, nodes


def _repository(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}
    repository = data.get("repository")
    return repository if isinstance(repository, dict) else {}


def _category_id(repository: dict[str, object]) -> str:
    wrapper = repository.get("discussionCategories")
    if not isinstance(wrapper, dict):
        return ""
    nodes = wrapper.get("nodes")
    if not isinstance(nodes, list):
        return ""
    named: str | None = None
    fallback: str | None = None
    for item in nodes:
        if not isinstance(item, dict):
            continue
        node_id = item.get("id")
        if not isinstance(node_id, str) or not node_id:
            continue
        if fallback is None:
            fallback = node_id
        if item.get("name") == "General":
            named = node_id
            break
    return named or fallback or ""


def _discussion_nodes_from_repo(repository: dict[str, object]) -> list[dict[str, object]]:
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
