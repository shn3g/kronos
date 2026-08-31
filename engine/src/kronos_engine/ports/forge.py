# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forge port. Application depends on this; the GitHub adapter implements it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME


class ForgeError(RuntimeError):
    """Base typed GitHub/forge failure."""


class DefaultBranchWriteRefused(ForgeError):
    """Raised when a command would write the protected default branch."""


class ForgeAuthError(ForgeError):
    """Raised when App credentials are missing or invalid. No PAT fallback."""


class ForgeRateLimited(ForgeError):
    """Raised after 403/429 backoff is exhausted."""


class ForgePermissionDenied(ForgeError):
    """Raised on a non-rate-limit 403."""


class ForgeTransientError(ForgeError):
    """Raised after 5xx backoff is exhausted."""


class RulesetWouldWeaken(ForgeError):
    """Raised when a ruleset payload would drop protections."""


class OperatorConfirmationRequired(ForgeError):
    """Raised when applying a ruleset without an explicit operator confirm."""


@dataclass(frozen=True, slots=True)
class ForgeTarget:
    owner: str
    repo: str
    integration_branch: str
    protected_branch: str


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    value: str


@dataclass(frozen=True, slots=True)
class IssueRef:
    number: int
    url: str
    created: bool


@dataclass(frozen=True, slots=True)
class CommentRef:
    id: int
    created: bool


@dataclass(frozen=True, slots=True)
class LabelChange:
    created: bool


@dataclass(frozen=True, slots=True)
class DiscussionRef:
    number: int
    url: str
    created: bool


@dataclass(frozen=True, slots=True)
class BranchRef:
    name: str
    sha: str
    created: bool


@dataclass(frozen=True, slots=True)
class PullRef:
    number: int
    url: str
    head: str
    base: str
    draft: bool
    created: bool
    head_sha: str = ""
    base_sha: str = ""


@dataclass(frozen=True, slots=True)
class RequiredCheck:
    context: str
    integration_id: int | None


@dataclass(frozen=True, slots=True)
class RulesetProposal:
    name: str
    required_checks: tuple[RequiredCheck, ...]
    strict: bool
    bypass_actors: tuple[Mapping[str, object], ...] = ()

    def replace_required_checks(self, checks: tuple[RequiredCheck, ...]) -> RulesetProposal:
        return replace(self, required_checks=checks)

    def replace_strict(self, strict: bool) -> RulesetProposal:
        return replace(self, strict=strict)

    def replace_bypass_actors(
        self, actors: tuple[Mapping[str, object], ...]
    ) -> RulesetProposal:
        return replace(self, bypass_actors=actors)

    def drop_integration_ids(self) -> RulesetProposal:
        return replace(
            self,
            required_checks=tuple(
                RequiredCheck(context=item.context, integration_id=None)
                for item in self.required_checks
            ),
        )


@dataclass(frozen=True, slots=True)
class RulesetRef:
    id: int
    strict: bool
    created: bool


@dataclass(frozen=True, slots=True)
class GithubAppRecord:
    role: str
    app_id: int
    slug: str
    installation_id: int | None = None
    verified_at: str | None = None

    @property
    def verified(self) -> bool:
        return self.verified_at is not None


@dataclass(frozen=True, slots=True)
class GithubAppStatus:
    registered: bool
    installed: bool
    verified: bool
    app_id: int | None = None
    slug: str | None = None


@dataclass(frozen=True, slots=True)
class GithubConnectionStatus:
    controller: GithubAppStatus
    reviewer: GithubAppStatus
    webhook_enabled: bool
    poll_mode: str
    github_cli_present: bool


@dataclass(frozen=True, slots=True)
class AppCredentials:
    app_id: int
    installation_id: int
    role: str = ""


class GithubAppStore(Protocol):
    def save(self, record: GithubAppRecord) -> None: ...

    def get(self, role: str) -> GithubAppRecord | None: ...

    def list(self) -> Sequence[GithubAppRecord]: ...


class Forge(Protocol):
    def create_issue(
        self,
        title: str,
        body: str,
        labels: Sequence[str],
        key: IdempotencyKey,
    ) -> IssueRef: ...

    def add_issue_comment(
        self, issue_number: int, body: str, key: IdempotencyKey
    ) -> CommentRef: ...

    def add_labels(
        self, issue_number: int, labels: Sequence[str], key: IdempotencyKey
    ) -> LabelChange: ...

    def create_discussion(
        self, title: str, body: str, key: IdempotencyKey
    ) -> DiscussionRef: ...

    def create_feature_branch(self, name: str, key: IdempotencyKey) -> BranchRef: ...

    def open_draft_pr(
        self,
        title: str,
        body: str,
        head: str,
        key: IdempotencyKey,
        *,
        base: str | None = None,
    ) -> PullRef: ...

    def list_issues(self) -> Sequence[IssueRef]: ...

    def propose_ruleset(self, reviewer_integration_id: int) -> RulesetProposal: ...

    def apply_ruleset(
        self, proposal: RulesetProposal, *, confirm: bool
    ) -> RulesetRef: ...


def provenance_marker(key: IdempotencyKey) -> str:
    return f"<!-- kronos:idemp:{key.value} -->"


def default_required_checks(reviewer_integration_id: int) -> tuple[RequiredCheck, ...]:
    return (
        RequiredCheck(context=KRONOS_REVIEW_CHECK_NAME, integration_id=reviewer_integration_id),
    )
