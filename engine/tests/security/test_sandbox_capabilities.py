# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sandbox capabilities: secret access, path escape, retries, and unsafe local mode."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.contract.test_repository_policy import _minimal_policy_dict
from tests.support.executor_fixtures import synthetic_request

from kronos_engine.adapters.executors.controlled import ControlledOpenExecutor
from kronos_engine.adapters.sandboxes.factory import default_sandbox, sandbox_for_policy
from kronos_engine.adapters.sandboxes.local_unsafe import LocalUnsafeSandbox
from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.domain.models import AttemptLimitExceeded
from kronos_engine.domain.policy import PolicyError, parse_policy
from kronos_engine.ports.sandbox import (
    CapabilityUnsupportedError,
    PathEscapeError,
    SandboxUnavailableError,
    SecretAccessError,
    UnsafeSandboxMergeRefused,
)


def test_default_sandbox_is_an_in_process_jail_without_false_isolation() -> None:
    sandbox = default_sandbox(Path("."))
    assert isinstance(sandbox, ProcessJailSandbox)
    caps = sandbox.capabilities()
    assert "jail" in caps.label.lower()
    assert "container" not in caps.label.lower()
    assert caps.network is True
    assert caps.root is True
    assert caps.secrets is False
    assert caps.unsafe is False
    assert caps.memory_mb == 0
    assert caps.cpu_limit == 0.0
    assert caps.allows_autonomous_merge is False


def test_docker_runtime_is_not_selected_until_it_confines() -> None:
    with pytest.raises(SandboxUnavailableError, match="Docker|SWE-ReX|confine"):
        sandbox_for_policy("docker", Path("."))


def test_jail_fails_closed_when_network_or_root_drop_is_requested(tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    sandbox = ProcessJailSandbox(worktree)
    with pytest.raises(CapabilityUnsupportedError, match="network"):
        ControlledOpenExecutor().run(
            synthetic_request(worktree, network=False, root=True), sandbox
        )
    with pytest.raises(CapabilityUnsupportedError, match="root"):
        ControlledOpenExecutor().run(
            synthetic_request(worktree, network=True, root=False), sandbox
        )


def test_secrets_false_rejects_secret_shaped_extra_env(tmp_path: Path) -> None:
    sandbox = ProcessJailSandbox(tmp_path / "wt")
    with pytest.raises(SecretAccessError, match="secret|credential|token"):
        sandbox.worker_environment({"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-extra"})
    env = sandbox.worker_environment({"PATH": "/usr/bin", "LANG": "C"})
    assert env == {"PATH": "/usr/bin", "LANG": "C"}


def test_secret_access_fails_deterministically(tmp_path: Path) -> None:
    sandbox = ProcessJailSandbox(tmp_path / "wt")
    with pytest.raises(SecretAccessError, match="secret|credential|token"):
        sandbox.worker_environment(
            {
                "PATH": "/usr/bin",
                "GH_TOKEN": "ghp_leak",
                "KRONOS_CONTROLLER_TOKEN": "controller",
                "KRONOS_REVIEWER_TOKEN": "reviewer",
            }
        )


def test_controller_and_reviewer_credential_leak_fails(tmp_path: Path) -> None:
    sandbox = ProcessJailSandbox(tmp_path / "wt")
    for key in (
        "KRONOS_AUTH_TOKEN",
        "GITHUB_APP_PRIVATE_KEY",
        "KRONOS_CONTROLLER_TOKEN",
        "KRONOS_REVIEWER_TOKEN",
    ):
        with pytest.raises(SecretAccessError):
            sandbox.worker_environment({"PATH": "/bin", key: "leak"})


def test_path_escape_fails_deterministically(tmp_path: Path) -> None:
    worktree = tmp_path / "cache" / "worktrees" / "repo_alpha" / "task_1"
    worktree.mkdir(parents=True)
    sandbox = ProcessJailSandbox(worktree)
    with pytest.raises(PathEscapeError):
        sandbox.write_text("../outside.txt", "nope")
    with pytest.raises(PathEscapeError):
        sandbox.write_text("/tmp/outside.txt", "nope")
    with pytest.raises(PathEscapeError):
        sandbox.write_text("ok/../../outside.txt", "nope")
    assert not (tmp_path / "cache" / "worktrees" / "repo_alpha" / "outside.txt").exists()
    sandbox.write_text("artifacts/hello.txt", "kronos-ok\n")
    assert (worktree / "artifacts" / "hello.txt").read_text(encoding="utf-8") == "kronos-ok\n"


def test_executor_rejects_escaped_artifact_path(tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    sandbox = ProcessJailSandbox(worktree)
    request = synthetic_request(worktree, artifact="../escape.txt")
    with pytest.raises(PathEscapeError):
        ControlledOpenExecutor().run(request, sandbox)
    assert not (tmp_path / "escape.txt").exists()


def test_unlimited_retries_fail_before_the_worker_runs(tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    sandbox = ProcessJailSandbox(worktree)
    with pytest.raises(AttemptLimitExceeded, match="unlimited"):
        ControlledOpenExecutor().run(synthetic_request(worktree, max_attempts=0), sandbox)


def test_local_unsandboxed_is_visibly_unsafe_and_cannot_merge(tmp_path: Path) -> None:
    sandbox = LocalUnsafeSandbox(tmp_path / "wt")
    caps = sandbox.capabilities()
    assert caps.unsafe is True
    assert "UNSAFE" in caps.label
    assert caps.allows_autonomous_merge is False
    with pytest.raises(UnsafeSandboxMergeRefused):
        sandbox.authorize_autonomous_merge()
    request = synthetic_request(tmp_path / "wt", autonomous_merge=True)
    with pytest.raises(UnsafeSandboxMergeRefused):
        ControlledOpenExecutor().run(request, sandbox)


def test_coder_may_merge_stays_unrepresentable() -> None:
    raw = _minimal_policy_dict()
    raw["autonomy"]["coder_may_merge"] = True  # type: ignore[index]
    with pytest.raises(PolicyError, match="unrepresentable|merge"):
        parse_policy(raw)
