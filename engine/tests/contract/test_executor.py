# SPDX-License-Identifier: AGPL-3.0-or-later
"""The same synthetic fixture must pass on both executors."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from tests.support.executor_fixtures import (
    SYNTHETIC_ARTIFACT,
    SYNTHETIC_CONTENT,
    synthetic_request,
)

from kronos_engine.adapters.executors.controlled import ControlledOpenExecutor
from kronos_engine.adapters.executors.cursor import CliResult, CursorExecutor
from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.ports.executor import Executor

ExecutorFactory = Callable[[Path], Executor]


def _controlled(_tmp_path: Path) -> Executor:
    return ControlledOpenExecutor()


def _cursor(_tmp_path: Path) -> Executor:
    def invoke(
        argv: list[str],
        env: dict[str, str],
        cwd: Path,
        timeout: float,
    ) -> CliResult:
        assert "--workspace" in argv
        assert env.get("GH_TOKEN") is None
        assert env.get("KRONOS_AUTH_TOKEN") is None
        assert env.get("KRONOS_CONTROLLER_TOKEN") is None
        assert env.get("KRONOS_REVIEWER_TOKEN") is None
        _ = cwd
        _ = timeout
        return CliResult(returncode=0, stdout=SYNTHETIC_CONTENT, stderr="")

    return CursorExecutor(
        which=lambda name: "C:/fake/cursor-agent" if name == "cursor-agent" else None,
        invoke=invoke,
    )


@pytest.mark.parametrize("factory", [_controlled, _cursor], ids=["controlled", "cursor"])
def test_synthetic_fixture_passes_on_both_executors(
    factory: ExecutorFactory, tmp_path: Path
) -> None:
    worktree = tmp_path / "cache" / "worktrees" / "repo_alpha" / "task_synthetic"
    sandbox = ProcessJailSandbox(worktree)
    request = synthetic_request(worktree)
    result = factory(tmp_path).run(request, sandbox)
    assert result.status == "succeeded"
    written = worktree / "artifacts" / "hello.txt"
    assert written.read_text(encoding="utf-8") == SYNTHETIC_CONTENT
    assert result.artifacts == (SYNTHETIC_ARTIFACT,)
    assert result.usage.attempts == 1
    assert result.usage.executor_id in {"controlled", "cursor"}
    assert request.repository_id.value == "repo_alpha"
    assert request.task_id.value == "task_synthetic"
    expected = tmp_path / "cache" / "worktrees" / "repo_alpha" / "task_synthetic"
    assert worktree.resolve() == expected.resolve()


def test_cursor_detection_does_not_run_repository_scripts(tmp_path: Path) -> None:
    repo = tmp_path / "enrolled"
    repo.mkdir()
    pwn = repo / "agent"
    pwn.write_text("import pathlib\npathlib.Path('PWNED').write_text('yes')\n", encoding="utf-8")
    detected = CursorExecutor(
        which=lambda name: (
            str(tmp_path / "bin" / "cursor-agent") if name == "cursor-agent" else None
        ),
    ).detect()
    assert detected is not None
    assert detected.name == "cursor-agent"
    assert not (repo / "PWNED").exists()
    assert not (tmp_path / "PWNED").exists()


def test_cursor_run_fails_when_stdout_empty_and_worker_did_not_write(tmp_path: Path) -> None:
    def invoke(
        argv: list[str], env: dict[str, str], cwd: Path, timeout: float
    ) -> CliResult:
        _ = argv
        _ = env
        _ = cwd
        _ = timeout
        return CliResult(returncode=0, stdout="", stderr="")

    executor = CursorExecutor(
        which=lambda name: "C:/fake/cursor-agent" if name == "cursor-agent" else None,
        invoke=invoke,
    )
    worktree = tmp_path / "wt"
    sandbox = ProcessJailSandbox(worktree)
    result = executor.run(synthetic_request(worktree), sandbox)
    assert result.status == "failed"
    assert not (worktree / "artifacts" / "hello.txt").exists()


def test_cursor_run_succeeds_when_worker_writes_artifact_without_stdout(tmp_path: Path) -> None:
    def invoke(
        argv: list[str], env: dict[str, str], cwd: Path, timeout: float
    ) -> CliResult:
        _ = argv
        _ = env
        _ = timeout
        artifact = cwd / "artifacts" / "hello.txt"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(SYNTHETIC_CONTENT, encoding="utf-8")
        return CliResult(returncode=0, stdout="", stderr="")

    executor = CursorExecutor(
        which=lambda name: "C:/fake/cursor-agent" if name == "cursor-agent" else None,
        invoke=invoke,
    )
    worktree = tmp_path / "wt"
    sandbox = ProcessJailSandbox(worktree)
    result = executor.run(synthetic_request(worktree), sandbox)
    assert result.status == "succeeded"
    assert (worktree / "artifacts" / "hello.txt").read_text(encoding="utf-8") == SYNTHETIC_CONTENT

