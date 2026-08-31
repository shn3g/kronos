# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evidence-gated promotion. Propose is not activate."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from kronos_engine.memory.records import (
    MemoryRecord,
    MemoryStatus,
    clamp_confidence,
    validate_memory_text,
)
from kronos_engine.skills.catalog import HumanApprovalRequired

if TYPE_CHECKING:
    from kronos_engine.skills.catalog import SkillCatalog


class PromotionBlocked(ValueError):
    """Raised when a candidate cannot be activated."""


@dataclass(frozen=True, slots=True)
class PromotionConfig:
    min_independent_helpful: int = 3


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    eligible: bool
    activated: bool
    reason: str
    needs_human: bool


def consider_promotion(
    catalog: SkillCatalog,
    target_id: str,
    config: PromotionConfig | None = None,
) -> PromotionDecision:
    cfg = config or PromotionConfig()
    record = _record(catalog, target_id)
    skill = _maybe_skill(catalog, record.skill_id or target_id)
    if record.status is MemoryStatus.disabled_candidate:
        return PromotionDecision(False, False, "disabled candidate", False)
    if record.status is MemoryStatus.rolled_back or record.harmful > 0:
        return PromotionDecision(False, False, "unresolved harmful", False)
    if skill is not None and skill.status in {"disabled", "rolled_back"}:
        return PromotionDecision(False, False, "skill rolled back", False)
    if record.status is MemoryStatus.active:
        return PromotionDecision(True, True, "already active", False)
    if len(record.independent_sources) < cfg.min_independent_helpful:
        return PromotionDecision(False, False, "insufficient evidence", False)
    needs_human = bool(skill is not None and skill.scope in {"core", "global"})
    return PromotionDecision(True, False, "proposed", needs_human)


def activate_promoted(
    catalog: SkillCatalog,
    skill_id: str,
    record_id: str | None = None,
    *,
    human: bool = False,
) -> MemoryRecord:
    record = _record(catalog, record_id or skill_id)
    skill = _maybe_skill(catalog, record.skill_id or skill_id)
    if skill is not None and skill.scope in {"core", "global"} and not human:
        raise HumanApprovalRequired("core skill changes need a human")
    if record.status is MemoryStatus.disabled_candidate:
        raise PromotionBlocked("disabled candidate cannot activate")
    if (
        record.status is MemoryStatus.rolled_back
        or record.harmful > 0
        or (skill is not None and skill.status in {"disabled", "rolled_back"})
    ):
        raise PromotionBlocked("disabled by harm rollback")
    decision = consider_promotion(catalog, record.id, PromotionConfig())
    if not decision.eligible:
        raise PromotionBlocked(decision.reason)
    updated = replace(record, status=MemoryStatus.active)
    return catalog.procedural.save(updated)


def record_outcome(
    catalog: SkillCatalog,
    *,
    skill_id: str,
    source_sha: str,
    outcome: str,
    text: str,
    confidence: float,
) -> MemoryRecord:
    body = validate_memory_text(text)
    conf = clamp_confidence(confidence)
    try:
        existing = catalog.procedural.for_skill(skill_id)
    except LookupError:
        existing = None
    if existing is None:
        independent = [source_sha] if outcome == "helpful" else []
        record = catalog.procedural.propose(
            text=body,
            source_sha=source_sha,
            confidence=conf,
            skill_id=skill_id,
            provenance={"outcome": outcome},
        )
        record = replace(
            record,
            outcome=outcome,
            helpful=1 if outcome == "helpful" else 0,
            harmful=1 if outcome == "harmful" else 0,
            independent_sources=tuple(independent),
            status=MemoryStatus.rolled_back if outcome == "harmful" else MemoryStatus.proposed,
        )
    else:
        independent = list(existing.independent_sources)
        helpful = existing.helpful
        harmful = existing.harmful
        if outcome == "helpful" and source_sha not in independent:
            independent.append(source_sha)
            helpful += 1
        if outcome == "harmful":
            harmful += 1
        status = MemoryStatus.rolled_back if harmful else existing.status
        if status is MemoryStatus.active and outcome == "harmful":
            status = MemoryStatus.rolled_back
        record = replace(
            existing,
            text=existing.text or body,
            outcome=outcome,
            confidence=conf,
            helpful=helpful,
            harmful=harmful,
            independent_sources=tuple(independent),
            status=status,
        )
    if outcome == "harmful":
        catalog.disable(skill_id, "harmful outcome")
        record = replace(record, status=MemoryStatus.rolled_back, harmful=max(record.harmful, 1))
    return catalog.procedural.save(record)


def _record(catalog: SkillCatalog, target_id: str) -> MemoryRecord:
    loaded = catalog.procedural.get(target_id)
    if loaded is not None:
        return loaded
    episodic = catalog.episodic.get(target_id)
    if episodic is not None:
        return episodic
    return catalog.procedural.for_skill(target_id)


def _maybe_skill(catalog: SkillCatalog, skill_id: str):  # type: ignore[no-untyped-def]
    try:
        return catalog.get(skill_id)
    except LookupError:
        return None
