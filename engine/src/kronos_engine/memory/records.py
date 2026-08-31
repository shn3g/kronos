# SPDX-License-Identifier: AGPL-3.0-or-later
"""Human-readable memory records. Text is authoritative. No I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_SECRET = re.compile(
    r"ghp_|gho_|ghu_|ghs_|github_pat_|sk-[A-Za-z0-9]|AKIA[0-9A-Z]{8}|"
    r"-----BEGIN|Bearer\s+[A-Za-z0-9._\-]+",
    re.I,
)
_COT = re.compile(r"<thinking>|</thinking>|chain-of-thought|chain of thought", re.I)


class MemoryRejected(ValueError):
    """Raised when a record would store secrets or hidden chain-of-thought."""


class MemoryKind(StrEnum):
    episodic = "episodic"
    procedural = "procedural"


class MemoryStatus(StrEnum):
    proposed = "proposed"
    disabled_candidate = "disabled_candidate"
    active = "active"
    rolled_back = "rolled_back"


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    kind: str
    text: str
    source_sha: str
    outcome: str
    confidence: float
    helpful: int
    harmful: int
    status: MemoryStatus
    independent_sources: tuple[str, ...]
    skill_id: str | None
    created_at: str
    provenance: dict[str, Any]
    run_id: str | None = None
    task_id: str | None = None


def validate_memory_text(text: str) -> str:
    if _SECRET.search(text):
        raise MemoryRejected("secret material cannot be stored as memory")
    if _COT.search(text):
        raise MemoryRejected("hidden chain-of-thought cannot be stored as memory")
    return text


def clamp_confidence(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)
