# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forge stand-in when GitHub is not configured. Merge still goes through MergeService."""

from __future__ import annotations

from kronos_engine.ports.forge import ForgeError, IdempotencyKey, PullRef


class UnavailableForge:
    integration_branch = "integration"
    protected_branch = "main"

    def create_feature_branch(self, name: str, key: IdempotencyKey) -> None:
        _ = name
        _ = key
        raise ForgeError("GitHub controller is not configured")

    def open_draft_pr(
        self, title: str, body: str, branch: str, key: IdempotencyKey
    ) -> PullRef:
        _ = title
        _ = body
        _ = branch
        _ = key
        raise ForgeError("GitHub controller is not configured")

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
        _ = title
        _ = body
        _ = head
        _ = base
        _ = draft
        _ = key
        raise ForgeError("GitHub controller is not configured")

    def merge_pull(self, number: int, *, sha: str, dest: str | None = None) -> None:
        _ = number
        _ = sha
        _ = dest
        raise ForgeError("GitHub controller is not configured")

    def get_pull(self, number: int) -> PullRef:
        _ = number
        raise ForgeError("GitHub controller is not configured")

    def list_check_runs(self, sha: str) -> tuple[object, ...]:
        _ = sha
        return ()

    def list_issue_comments(self, number: int) -> tuple[object, ...]:
        _ = number
        return ()

    def list_issue_labels(self, number: int) -> tuple[str, ...]:
        _ = number
        return ()

    def ruleset_strict(self) -> bool:
        return True

    def review_threads_resolved(self, number: int) -> bool:
        _ = number
        return True

    def file_at_sha(self, sha: str, path: str) -> str:
        _ = sha
        _ = path
        raise ForgeError("GitHub controller is not configured")
