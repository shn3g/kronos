# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load Agent Skills directories. Filesystem I/O only."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.skills.manifest import SkillManifest, parse_skill_md


def load_skill_dir(path: Path) -> SkillManifest:
    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md missing in {path}")
    return parse_skill_md(skill_md.read_text(encoding="utf-8"))


def load_library(root: Path) -> tuple[SkillManifest, ...]:
    if not root.is_dir():
        return ()
    loaded: list[SkillManifest] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.is_dir() and (child / "SKILL.md").is_file():
            loaded.append(load_skill_dir(child))
    return tuple(loaded)
