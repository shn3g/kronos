# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression and security evaluation. Static; does not run skill scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from kronos_engine.domain.policy_yaml import parse_simple_yaml

_NEGATION_PREFIX = re.compile(
    r"(?:do\s+not|don't|dont|never|must\s+not|should\s+not)\s+$",
    re.I,
)

if TYPE_CHECKING:
    from kronos_engine.skills.catalog import InstalledSkill


@dataclass(frozen=True, slots=True)
class RegressionContract:
    skill: str
    prompt: str
    verification: tuple[str, ...]
    forbidden: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    passed: bool
    security_passed: bool
    regression_passed: bool
    reasons: tuple[str, ...]


def load_regression_contract(path: Path) -> RegressionContract:
    parsed = parse_simple_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("regression contract must be a mapping")
    verification = parsed.get("verification") or []
    forbidden = parsed.get("forbidden") or []
    if not isinstance(verification, list) or not isinstance(forbidden, list):
        raise ValueError("verification and forbidden must be lists")
    return RegressionContract(
        skill=str(parsed.get("skill") or path.stem),
        prompt=str(parsed.get("prompt") or ""),
        verification=tuple(str(item) for item in verification),
        forbidden=tuple(str(item) for item in forbidden),
    )


def evaluate_skill(
    skill: InstalledSkill,
    contract: RegressionContract | None = None,
) -> EvaluationResult:
    security_passed = not skill.scan.malicious
    reasons: list[str] = []
    if not security_passed:
        reasons.append("malicious scan")
    chosen = contract or skill.contract
    regression_passed = True
    if chosen is None:
        regression_passed = False
        reasons.append("missing regression contract")
    else:
        haystack = f"{skill.manifest.description}\n{skill.manifest.body}".lower()
        missing = [item for item in chosen.verification if item.lower() not in haystack]
        forbidden = [item for item in chosen.forbidden if _forbidden_violated(haystack, item)]
        if missing:
            regression_passed = False
            reasons.append("regression contract unmet")
        if forbidden:
            regression_passed = False
            reasons.append("forbidden phrase")
    passed = security_passed and regression_passed
    return EvaluationResult(
        passed=passed,
        security_passed=security_passed,
        regression_passed=regression_passed,
        reasons=tuple(reasons),
    )


def _forbidden_violated(haystack: str, phrase: str) -> bool:
    needle = phrase.lower()
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        prefix = haystack[max(0, index - 40) : index]
        if not _NEGATION_PREFIX.search(prefix):
            return True
        start = index + 1
