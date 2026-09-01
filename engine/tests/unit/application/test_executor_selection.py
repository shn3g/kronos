# SPDX-License-Identifier: AGPL-3.0-or-later
"""Executor profile selection: standard aliases controlled; CLI falls back when missing."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from tests.support.executor_fixtures import synthetic_request

from kronos_engine.adapters.executors.controlled import ControlledOpenExecutor
from kronos_engine.adapters.executors.cursor import CliResult, CursorCli, CursorExecutor
from kronos_engine.adapters.executors.opencode import OpencodeExecutor
from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.application.composition import RepositoryPolicyExecutor, select_executor
from kronos_engine.domain.entities import EnrolledRepository, RepositoryId, RepositoryStatus
from kronos_engine.domain.policy import (
    RepositoryPolicy,
    default_policy,
    parse_policy,
    policy_to_dict,
)


def test_standard_profile_is_controlled() -> None:
    executor = select_executor("standard")
    assert isinstance(executor, ControlledOpenExecutor)


def test_controlled_profile_is_controlled() -> None:
    executor = select_executor("controlled")
    assert isinstance(executor, ControlledOpenExecutor)


def test_cursor_profile_uses_cursor_when_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_cursor_cli",
        lambda: object(),
    )
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_opencode_cli",
        lambda: None,
    )
    executor = select_executor("cursor")
    assert isinstance(executor, CursorExecutor)


def test_cursor_profile_falls_back_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_cursor_cli",
        lambda: None,
    )
    executor = select_executor("cursor")
    assert isinstance(executor, ControlledOpenExecutor)


def test_opencode_profile_uses_opencode_when_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_cursor_cli",
        lambda: None,
    )
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_opencode_cli",
        lambda: object(),
    )
    executor = select_executor("opencode")
    assert isinstance(executor, OpencodeExecutor)


def test_opencode_profile_falls_back_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_opencode_cli",
        lambda: None,
    )
    executor = select_executor("opencode")
    assert isinstance(executor, ControlledOpenExecutor)


def _policy_with_executor(profile: str) -> RepositoryPolicy:
    raw = policy_to_dict(default_policy(integration_branch="main", protected_branch="main"))
    raw["executor"] = {"profile": profile, "sandbox": "default"}
    return parse_policy(raw)


def _enrolled(repo_id: str, profile: str) -> EnrolledRepository:
    return EnrolledRepository(
        id=RepositoryId(repo_id),
        realpath="/tmp/enrolled/" + repo_id,
        origin="https://github.com/acme/" + repo_id + ".git",
        display_name=repo_id,
        status=RepositoryStatus.ACTIVE,
        policy=_policy_with_executor(profile),
        enrolled_at="2026-08-31T12:00:00+00:00",
    )


class _RepoMap:
    def __init__(self, records: tuple[EnrolledRepository, ...]) -> None:
        self._records = {item.id.value: item for item in records}

    def get(self, repo_id: RepositoryId) -> EnrolledRepository:
        return self._records[repo_id.value]


def test_mixed_repo_policies_dispatch_matching_executors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_cursor_cli",
        lambda: CursorCli(path="/fake/cursor-agent", name="cursor-agent"),
    )
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_opencode_cli",
        lambda: None,
    )
    monkeypatch.setattr(
        "kronos_engine.adapters.executors.cursor.detect_cursor_cli",
        lambda which=None, environ=None: CursorCli(
            path="/fake/cursor-agent", name="cursor-agent"
        ),
    )
    monkeypatch.setattr(
        "kronos_engine.adapters.executors.cursor._subprocess_invoke",
        lambda argv, env, cwd, timeout: CliResult(returncode=0, stdout="ok\n", stderr=""),
    )
    cursor_repo = _enrolled("repo_cursor", "cursor")
    controlled_repo = _enrolled("repo_controlled", "controlled")
    router = RepositoryPolicyExecutor(_RepoMap((cursor_repo, controlled_repo)))

    cursor_tree = tmp_path / "cursor"
    controlled_tree = tmp_path / "controlled"
    cursor_result = router.run(
        replace(synthetic_request(cursor_tree), repository_id=cursor_repo.id),
        ProcessJailSandbox(cursor_tree),
    )
    controlled_result = router.run(
        replace(synthetic_request(controlled_tree), repository_id=controlled_repo.id),
        ProcessJailSandbox(controlled_tree),
    )
    assert cursor_result.status == "succeeded"
    assert controlled_result.status == "succeeded"
    assert cursor_result.usage.executor_id == "cursor"
    assert controlled_result.usage.executor_id == "controlled"
    assert cursor_result.usage.executor_id != controlled_result.usage.executor_id
