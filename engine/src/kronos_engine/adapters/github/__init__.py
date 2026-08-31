# SPDX-License-Identifier: AGPL-3.0-or-later
"""GitHub controller adapter. Implements the Forge port."""

from __future__ import annotations

from collections.abc import Sequence

from kronos_engine.adapters.github.auth import InstallationAuth
from kronos_engine.adapters.github.branches import create_feature_branch as _create_branch
from kronos_engine.adapters.github.checks import assert_controller_cannot_post
from kronos_engine.adapters.github.client import GitHubClient
from kronos_engine.adapters.github.discussions import create_discussion as _create_discussion
from kronos_engine.adapters.github.issues import add_issue_comment as _add_comment
from kronos_engine.adapters.github.issues import add_labels as _add_labels
from kronos_engine.adapters.github.issues import create_issue as _create_issue
from kronos_engine.adapters.github.issues import list_issues as _list_issues
from kronos_engine.adapters.github.observe import file_at_sha as _file_at_sha
from kronos_engine.adapters.github.observe import list_check_runs as _list_check_runs
from kronos_engine.adapters.github.observe import list_issue_comments as _list_issue_comments
from kronos_engine.adapters.github.observe import list_issue_labels as _list_issue_labels
from kronos_engine.adapters.github.observe import observed_pull as _observed_pull
from kronos_engine.adapters.github.observe import (
    review_threads_resolved as _review_threads_resolved,
)
from kronos_engine.adapters.github.observe import ruleset_strict as _ruleset_strict
from kronos_engine.adapters.github.pulls import merge_pull as _merge_pull
from kronos_engine.adapters.github.pulls import open_draft_pr as _open_draft_pr
from kronos_engine.adapters.github.pulls import open_promotion_pr as _open_promotion_pr
from kronos_engine.adapters.github.rulesets import apply_ruleset as _apply_ruleset
from kronos_engine.adapters.github.rulesets import propose_ruleset as _propose_ruleset
from kronos_engine.ports.forge import (
    BranchRef,
    CommentRef,
    DiscussionRef,
    ForgeTarget,
    IdempotencyKey,
    IssueRef,
    LabelChange,
    PullRef,
    RulesetProposal,
    RulesetRef,
)


class GitHubForge:
    def __init__(self, client: GitHubClient, target: ForgeTarget) -> None:
        self._client = client
        self._target = target

    def create_issue(
        self,
        title: str,
        body: str,
        labels: Sequence[str],
        key: IdempotencyKey,
    ) -> IssueRef:
        return _create_issue(self._client, self._target, title, body, labels, key)

    def add_issue_comment(
        self, issue_number: int, body: str, key: IdempotencyKey
    ) -> CommentRef:
        return _add_comment(self._client, self._target, issue_number, body, key)

    def add_labels(
        self, issue_number: int, labels: Sequence[str], key: IdempotencyKey
    ) -> LabelChange:
        return _add_labels(self._client, self._target, issue_number, labels, key)

    def create_discussion(
        self, title: str, body: str, key: IdempotencyKey
    ) -> DiscussionRef:
        return _create_discussion(self._client, self._target, title, body, key)

    def create_feature_branch(self, name: str, key: IdempotencyKey) -> BranchRef:
        return _create_branch(self._client, self._target, name, key)

    def open_draft_pr(
        self,
        title: str,
        body: str,
        head: str,
        key: IdempotencyKey,
        *,
        base: str | None = None,
    ) -> PullRef:
        return _open_draft_pr(
            self._client, self._target, title, body, head, key, base=base
        )

    def merge_pull(
        self, number: int, *, sha: str, dest: str | None = None, target: str | None = None
    ) -> None:
        chosen = dest if dest is not None else target
        _merge_pull(self._client, self._target, number, sha=sha, dest=chosen)

    def get_pull(self, number: int) -> PullRef:
        return _observed_pull(self._client, self._target, number)

    def list_check_runs(self, sha: str) -> tuple[dict[str, object], ...]:
        return tuple(dict(item) for item in _list_check_runs(self._client, self._target, sha))

    def list_issue_comments(self, number: int) -> tuple[dict[str, object], ...]:
        comments = _list_issue_comments(self._client, self._target, number)
        return tuple(dict(item) for item in comments)

    def list_issue_labels(self, number: int) -> tuple[str, ...]:
        return _list_issue_labels(self._client, self._target, number)

    def ruleset_strict(self) -> bool:
        return _ruleset_strict(self._client, self._target)

    def review_threads_resolved(self, number: int) -> bool:
        return _review_threads_resolved(self._client, self._target, number)

    def file_at_sha(self, sha: str, path: str) -> str:
        return _file_at_sha(self._client, self._target, sha, path)

    @property
    def integration_branch(self) -> str:
        return self._target.integration_branch

    @property
    def protected_branch(self) -> str:
        return self._target.protected_branch

    def open_pull(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool,
        key: IdempotencyKey,
    ) -> PullRef:
        _ = draft
        if base == self._target.protected_branch:
            return _open_promotion_pr(self._client, self._target, title, body, head, key)
        return _open_draft_pr(
            self._client, self._target, title, body, head, key, base=base
        )

    def list_issues(self) -> tuple[IssueRef, ...]:
        return _list_issues(self._client, self._target)

    def propose_ruleset(self, reviewer_integration_id: int) -> RulesetProposal:
        return _propose_ruleset(self._client, self._target, reviewer_integration_id)

    def apply_ruleset(self, proposal: RulesetProposal, *, confirm: bool) -> RulesetRef:
        return _apply_ruleset(self._client, self._target, proposal, confirm=confirm)

    def post_check_run(self, *, head_sha: str, name: str, conclusion: str) -> None:
        _ = head_sha
        _ = conclusion
        assert_controller_cannot_post(name)


__all__ = ["GitHubForge", "GitHubClient", "InstallationAuth"]
