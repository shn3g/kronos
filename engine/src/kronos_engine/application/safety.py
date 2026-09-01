# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed GitHub write safety: ruleset, workflow, CODEOWNERS, reviewer app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kronos_engine.application.unavailable_forge import UnavailableForge
from kronos_engine.domain.entities import EnrolledRepository
from kronos_engine.ports.forge import GithubAppRecord

SAFETY_CHECK_IDS: tuple[str, ...] = (
    "ruleset_strict",
    "kronos_pr_workflow",
    "codeowners",
    "reviewer_app",
)


class SafetyElevationRefused(RuntimeError):
    """Raised when PR-write mode elevation is blocked by safety checks."""

    def __init__(self, report: SafetyReport) -> None:
        self.report = report
        super().__init__("repository safety checks refuse write elevation")


@dataclass(frozen=True, slots=True)
class SafetyCheck:
    id: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class SafetyReport:
    ok: bool
    checks: tuple[SafetyCheck, ...]


def evaluate_repository_safety(
    record: EnrolledRepository,
    *,
    forge: object | None,
    reviewer: GithubAppRecord | None,
) -> SafetyReport:
    root = Path(record.realpath)
    checks = (
        _ruleset_check(forge),
        _file_check(
            "kronos_pr_workflow",
            root / ".github" / "workflows" / "kronos-pr.yml",
            "Kronos PR workflow",
        ),
        _file_check("codeowners", root / ".github" / "CODEOWNERS", "CODEOWNERS"),
        _reviewer_check(reviewer),
    )
    return SafetyReport(ok=all(item.ok for item in checks), checks=checks)


def _ruleset_check(forge: object | None) -> SafetyCheck:
    if forge is None or isinstance(forge, UnavailableForge):
        return SafetyCheck(
            id="ruleset_strict",
            ok=False,
            detail="GitHub controller is not configured",
        )
    method = getattr(forge, "ruleset_strict", None)
    if not callable(method):
        return SafetyCheck(
            id="ruleset_strict",
            ok=False,
            detail="forge cannot report ruleset strictness",
        )
    try:
        ok = bool(method())
    except Exception as error:  # noqa: BLE001 — fail closed on any forge error
        return SafetyCheck(id="ruleset_strict", ok=False, detail=str(error))
    detail = "strict required status checks are enabled" if ok else "ruleset is not strict"
    return SafetyCheck(id="ruleset_strict", ok=ok, detail=detail)


def _file_check(check_id: str, path: Path, label: str) -> SafetyCheck:
    if path.is_file():
        return SafetyCheck(id=check_id, ok=True, detail=f"{label} is present")
    return SafetyCheck(id=check_id, ok=False, detail=f"{label} is missing")


def _reviewer_check(reviewer: GithubAppRecord | None) -> SafetyCheck:
    if reviewer is None or reviewer.installation_id is None:
        return SafetyCheck(
            id="reviewer_app",
            ok=False,
            detail="reviewer GitHub App is not installed",
        )
    if reviewer.verified_at is None:
        return SafetyCheck(
            id="reviewer_app",
            ok=False,
            detail="reviewer GitHub App is not verified",
        )
    return SafetyCheck(
        id="reviewer_app",
        ok=True,
        detail="reviewer GitHub App is installed and verified",
    )
