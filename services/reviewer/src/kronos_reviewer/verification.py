# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recalculate risk, inspect protected paths, and rerun required commands."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kronos_engine.domain.attestations import CommandOutcome
from kronos_engine.domain.policy import RepositoryPolicy, clamp_risk


class VerificationError(RuntimeError):
    """Raised when required commands or sandbox freshness fail."""


class CommandRunner(Protocol):
    def start_fresh(self) -> str: ...

    def run(
        self, argv: Sequence[str], *, worktree: Path, sandbox_id: str
    ) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    reason: str
    risk: str
    commands: tuple[CommandOutcome, ...]
    sandbox_id: str
    protected_path_hit: bool


def verify_change(
    *,
    policy: RepositoryPolicy,
    changed_files: Sequence[str],
    proposed_risk: str,
    runner: CommandRunner,
    worktree: Path,
) -> VerificationResult:
    protected_path_hit = _protected_path_hit(changed_files, policy.paths.locked_prefixes)
    risk = policy.risk.floor
    if protected_path_hit:
        risk = clamp_risk(risk, "high")
    risk = clamp_risk(risk, proposed_risk)
    sandbox_id = runner.start_fresh()
    outcomes: list[CommandOutcome] = []
    for argv in _required_commands(policy):
        raw = runner.run(argv, worktree=worktree, sandbox_id=sandbox_id)
        outcome = _outcome(raw)
        outcomes.append(outcome)
        if not outcome.sandbox_fresh:
            raise VerificationError("required commands must rerun in a fresh sandbox")
        if outcome.exit_code != 0:
            raise VerificationError(f"required command failed: {' '.join(outcome.argv)}")
    return VerificationResult(
        ok=True,
        reason="verified",
        risk=risk,
        commands=tuple(outcomes),
        sandbox_id=sandbox_id,
        protected_path_hit=protected_path_hit,
    )


def _required_commands(policy: RepositoryPolicy) -> tuple[tuple[str, ...], ...]:
    groups = (
        policy.commands.setup,
        policy.commands.test,
        policy.commands.lint,
        policy.commands.build,
    )
    return tuple(group for group in groups if group)


def _protected_path_hit(changed_files: Sequence[str], prefixes: Sequence[str]) -> bool:
    for path in changed_files:
        normalized = path.replace("\\", "/")
        for prefix in prefixes:
            needle = prefix.replace("\\", "/")
            if needle.endswith("/"):
                if normalized.startswith(needle):
                    return True
            elif normalized == needle or normalized.startswith(f"{needle}/"):
                return True
    return False


def _outcome(raw: dict[str, object]) -> CommandOutcome:
    argv = raw.get("argv")
    if not isinstance(argv, list):
        raise VerificationError("command argv missing")
    exit_code = raw.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise VerificationError("command exit_code missing")
    sandbox_fresh = raw.get("sandbox_fresh")
    if not isinstance(sandbox_fresh, bool):
        raise VerificationError("sandbox_fresh missing")
    return CommandOutcome(
        argv=tuple(str(item) for item in argv),
        exit_code=exit_code,
        sandbox_fresh=sandbox_fresh,
    )
