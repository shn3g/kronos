# SPDX-License-Identifier: AGPL-3.0-or-later
"""Risk, protected paths, and fresh-sandbox command reruns."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.support import FakeRunner, policy_mapping

from kronos_engine.domain.policy import parse_policy
from kronos_reviewer.verification import VerificationError, verify_change


def _policy(**kwargs: object):
    return parse_policy(policy_mapping(**kwargs))


def test_protected_path_change_raises_risk_and_cannot_be_talked_down(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    result = verify_change(
        policy=_policy(risk="medium", locked=("engine/src/kronos_engine/domain/",)),
        changed_files=("engine/src/kronos_engine/domain/attestations.py",),
        proposed_risk="low",
        runner=runner,
        worktree=tmp_path,
    )
    assert result.ok is True
    assert result.risk == "high"
    assert result.protected_path_hit is True


def test_required_commands_rerun_in_fresh_sandbox(tmp_path: Path) -> None:
    runner = FakeRunner()
    result = verify_change(
        policy=_policy(test=("pytest", "-q")),
        changed_files=("README.md",),
        proposed_risk="medium",
        runner=runner,
        worktree=tmp_path,
    )
    assert result.ok is True
    assert runner.runs == [(("pytest", "-q"), result.sandbox_id)]
    assert all(command.sandbox_fresh for command in result.commands)


def test_reused_sandbox_fails_verification(tmp_path: Path) -> None:
    runner = FakeRunner(reuse=True)
    with pytest.raises(VerificationError, match="sandbox"):
        verify_change(
            policy=_policy(test=("pytest", "-q")),
            changed_files=("README.md",),
            proposed_risk="medium",
            runner=runner,
            worktree=tmp_path,
        )


def test_failed_required_command_fails_verification(tmp_path: Path) -> None:
    runner = FakeRunner(exit_codes={("pytest", "-q"): 1})
    with pytest.raises(VerificationError, match="command|pytest"):
        verify_change(
            policy=_policy(test=("pytest", "-q")),
            changed_files=("README.md",),
            proposed_risk="medium",
            runner=runner,
            worktree=tmp_path,
        )
