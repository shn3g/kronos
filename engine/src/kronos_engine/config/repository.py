# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repository policy templates and previewable diffs. Never writes the tree."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.policy import RepositoryPolicy, policy_to_dict

TEMPLATES_ROOT = Path(__file__).resolve().parents[4] / "templates"


@dataclass(frozen=True, slots=True)
class PreviewFile:
    path: str
    action: str
    content: str
    unified_diff: str


@dataclass(frozen=True, slots=True)
class EnrolmentPreview:
    files: tuple[PreviewFile, ...]
    wrote_files: bool = False
    committed: bool = False
    pushed: bool = False


def github_owner_repo(origin: str | None) -> tuple[str, str] | None:
    if origin is None or origin.strip() == "":
        return None
    text = origin.strip().rstrip("/").removesuffix(".git")
    rest: str | None = None
    if "github.com:" in text:
        rest = text.split("github.com:", 1)[1]
    elif "github.com/" in text:
        rest = text.split("github.com/", 1)[1]
    if rest is None:
        return None
    parts = [item for item in rest.split("/") if item]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def github_owner(origin: str | None) -> str:
    parsed = github_owner_repo(origin)
    if parsed is None:
        return "@codeowners"
    return f"@{parsed[0]}"


def render_enrolment_preview(
    git_root: Path,
    policy: RepositoryPolicy,
    owner: str,
) -> EnrolmentPreview:
    files = (
        _preview_file(git_root, ".kronos/config.yaml", render_config_yaml(policy)),
        _preview_file(git_root, ".github/workflows/kronos-pr.yml", _workflow_template()),
        _preview_file(git_root, ".github/CODEOWNERS", _codeowners_content(git_root, owner)),
    )
    return EnrolmentPreview(files=files, wrote_files=False, committed=False, pushed=False)


def render_config_yaml(policy: RepositoryPolicy) -> str:
    return _emit_yaml(policy_to_dict(policy)) + "\n"


def _workflow_template() -> str:
    path = TEMPLATES_ROOT / "github" / "kronos-pr.yml"
    return path.read_text(encoding="utf-8")


def _codeowners_content(git_root: Path, owner: str) -> str:
    additions = (
        f".kronos/** {owner}\n"
        f".github/workflows/kronos-pr.yml {owner}\n"
    )
    existing_path = git_root / ".github" / "CODEOWNERS"
    if not existing_path.is_file():
        return additions
    existing = existing_path.read_text(encoding="utf-8")
    if not existing.endswith("\n"):
        existing += "\n"
    for line in additions.splitlines():
        if line not in existing:
            existing += line + "\n"
    return existing


def _preview_file(git_root: Path, relative: str, content: str) -> PreviewFile:
    current_path = git_root / relative
    original = current_path.read_text(encoding="utf-8") if current_path.is_file() else ""
    action = "update" if original else "add"
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile="/dev/null" if original == "" else f"a/{relative}",
            tofile=f"b/{relative}",
        )
    )
    return PreviewFile(path=relative, action=action, content=content, unified_diff=diff)


def _emit_yaml(value: object, indent: int = 0) -> str:
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            prefix = "  " * indent + str(key)
            if isinstance(item, dict):
                lines.append(f"{prefix}:")
                lines.append(_emit_yaml(item, indent + 1))
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{prefix}: []")
                else:
                    lines.append(f"{prefix}:")
                    lines.append(_emit_yaml(item, indent + 1))
            else:
                lines.append(f"{prefix}: {_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            lines.append("  " * indent + "- " + _scalar(item))
        return "\n".join(lines)
    return "  " * indent + _scalar(value)


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    if text == "" or text[:1] in "-?:" or any(ch.isspace() for ch in text) or ":" in text:
        return '"' + text.replace('"', '\\"') + '"'
    return text
