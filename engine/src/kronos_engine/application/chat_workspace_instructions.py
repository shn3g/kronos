# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read known workspace instruction files. Stays inside the repo root."""

from __future__ import annotations

from pathlib import Path

MAX_WORKSPACE_INSTRUCTION_CHARS = 12_000
ROOT_INSTRUCTION_FILES = ("AGENTS.md", ".cursorrules", "CLAUDE.md")
RULE_DIR = Path(".cursor") / "rules"
RULE_SUFFIXES = {".md", ".mdc", ".txt"}


def workspace_instruction_text(root: Path) -> str:
    resolved = root.resolve()
    blocks: list[str] = []
    remaining = MAX_WORKSPACE_INSTRUCTION_CHARS
    for rel in _instruction_relpaths(resolved):
        body = _read_instruction_file(resolved, rel)
        if body is None or body.strip() == "":
            continue
        header = f"{rel.as_posix()}\n"
        if remaining <= len(header):
            break
        room = remaining - len(header)
        clipped = body if len(body) <= room else body[:room]
        blocks.append(f"{header}{clipped}")
        remaining -= len(header) + len(clipped)
        if remaining <= 0:
            break
    return "\n\n".join(blocks)


def _instruction_relpaths(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = [Path(name) for name in ROOT_INSTRUCTION_FILES]
    rules = (root / RULE_DIR).resolve()
    if not _is_inside(root, rules) or not rules.is_dir():
        return tuple(paths)
    children = sorted(rules.iterdir(), key=lambda item: item.name.lower())
    for child in children:
        if not child.is_file() or child.suffix.lower() not in RULE_SUFFIXES:
            continue
        target = child.resolve()
        if not _is_inside(root, target):
            continue
        paths.append(target.relative_to(root))
    return tuple(paths)


def _read_instruction_file(root: Path, rel: Path) -> str | None:
    if rel.is_absolute() or any(part in {"..", ".git"} for part in rel.parts):
        return None
    target = (root / rel).resolve()
    if not _is_inside(root, target) or not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _is_inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True
