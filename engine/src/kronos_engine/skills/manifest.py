# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent Skills SKILL.md manifest parsing. No I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from kronos_engine.domain.policy_yaml import parse_simple_yaml

_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillManifestError(ValueError):
    """Raised when SKILL.md frontmatter is missing or invalid."""


@dataclass(frozen=True, slots=True)
class SkillManifest:
    name: str
    description: str
    license: str | None
    compatibility: str | None
    allowed_tools: tuple[str, ...]
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    scope: str
    metadata: dict[str, Any]
    body: str

    @property
    def summary(self) -> str:
        return f"{self.name}: {self.description}"


def estimate_tokens(text: str) -> int:
    return len(text.split())


def parse_skill_md(text: str) -> SkillManifest:
    if not text.startswith("---"):
        raise SkillManifestError("SKILL.md must start with YAML frontmatter")
    rest = text[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end < 0:
        raise SkillManifestError("SKILL.md frontmatter is not terminated")
    raw = rest[:end]
    body = rest[end + 4 :].lstrip("\n")
    parsed = parse_simple_yaml(raw)
    if not isinstance(parsed, dict):
        raise SkillManifestError("SKILL.md frontmatter must be a mapping")
    name = parsed.get("name")
    description = parsed.get("description")
    if not isinstance(name, str) or name.strip() == "":
        raise SkillManifestError("name is required")
    if not _NAME.match(name) or len(name) > 64:
        raise SkillManifestError("name must be lowercase alphanumeric with hyphens")
    if not isinstance(description, str) or description.strip() == "":
        raise SkillManifestError("description is required")
    metadata = parsed.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise SkillManifestError("metadata must be a mapping")
    allowed = parsed.get("allowed-tools", parsed.get("allowed_tools", ""))
    if isinstance(allowed, str):
        tools = tuple(item for item in allowed.split() if item)
    elif isinstance(allowed, list):
        tools = tuple(str(item) for item in allowed)
    else:
        tools = ()
    capabilities = _string_tuple(metadata.get("capabilities"))
    permissions = _string_tuple(metadata.get("permissions"))
    scope_raw = metadata.get("scope", "community")
    scope = str(scope_raw) if scope_raw else "community"
    license_raw = parsed.get("license")
    compatibility_raw = parsed.get("compatibility")
    return SkillManifest(
        name=name,
        description=description.strip(),
        license=str(license_raw) if license_raw else None,
        compatibility=str(compatibility_raw) if compatibility_raw else None,
        allowed_tools=tools,
        capabilities=capabilities,
        permissions=permissions,
        scope=scope,
        metadata=dict(metadata),
        body=body,
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()
