# SPDX-License-Identifier: AGPL-3.0-or-later
"""Route relevant skill summaries inside an explicit token budget."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from kronos_engine.skills.manifest import SkillManifest, estimate_tokens

if TYPE_CHECKING:
    from kronos_engine.skills.catalog import InstalledSkill

_TOKEN = r"[a-z0-9]+"
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "from",
        "by",
        "is",
        "at",
        "as",
        "it",
        "be",
    }
)


@dataclass(frozen=True, slots=True)
class RoutedSkills:
    summaries: tuple[SkillManifest, ...]
    selected: SkillManifest | None
    omitted: tuple[str, ...]
    tokens_used: int


def route_skills(
    query: str,
    skills: Sequence[InstalledSkill],
    *,
    budget_tokens: int,
    selected_name: str | None = None,
) -> RoutedSkills:
    query_tokens = _tokens(query)
    ranked: list[tuple[int, SkillManifest]] = []
    omitted: list[str] = []
    for item in skills:
        if item.status != "active":
            omitted.append(item.name)
            continue
        manifest = item.manifest
        haystack = f"{manifest.name.replace('-', ' ')} {manifest.description}"
        score = len(query_tokens & _tokens(haystack))
        if score <= 0:
            omitted.append(manifest.name)
            continue
        ranked.append((score, manifest))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].name))
    summaries: list[SkillManifest] = []
    tokens_used = 0
    for _score, manifest in ranked:
        summary = replace(manifest, body="")
        cost = estimate_tokens(f"{summary.name} {summary.description}")
        if tokens_used + cost > budget_tokens:
            omitted.append(manifest.name)
            continue
        summaries.append(summary)
        tokens_used += cost
    selected: SkillManifest | None = None
    if selected_name:
        match = next(
            (manifest for _score, manifest in ranked if manifest.name == selected_name),
            None,
        )
        if match is not None:
            selected = match
            tokens_used += estimate_tokens(match.body)
    return RoutedSkills(
        summaries=tuple(summaries),
        selected=selected,
        omitted=tuple(omitted),
        tokens_used=tokens_used,
    )


def _tokens(text: str) -> set[str]:
    return {match.group(0) for match in re.finditer(_TOKEN, text.lower())} - _STOP
