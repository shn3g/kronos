# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quarantine installs and static scans. Never execute untrusted skill scripts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kronos_engine.skills.loader import load_skill_dir

_SHA = re.compile(r"^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$")
_NETWORK = re.compile(
    r"urllib|requests\.|httpx|aiohttp|socket\.|Invoke-WebRequest|\bcurl\b|\bwget\b",
    re.I,
)
_SECRETS = re.compile(
    r"GH_TOKEN|OPENAI_API_KEY|KRONOS_REVIEWER|KRONOS_CONTROLLER|"
    r"BEGIN [A-Z ]+PRIVATE KEY|github_pat_|ghp_|gho_",
    re.I,
)
_EVAL = re.compile(r"\beval\s*\(|\bexec\s*\(|os\.system|subprocess")
_ESCAPE = re.compile(r"(?:\.\./|\.\.\\)")
_SCRIPT_SUFFIXES = {".py", ".sh", ".ps1", ".js", ".bash", ".zsh", ".cmd", ".bat"}
_REF = re.compile(r"(?:`([^`]+)`)|(?:\[[^\]]*\]\(([^)]+)\))")


class MutableRevisionError(ValueError):
    """Raised when a skill locator uses a moving tag or branch."""


class NetworkFetchForbidden(ValueError):
    """Raised when community HTTP fetch is attempted."""


class SkillStillQuarantined(ValueError):
    """Raised when a quarantined or malicious skill is activated."""


class SkillSourcePort(Protocol):
    def fetch(self, locator: str, revision: str) -> Path: ...


@dataclass(frozen=True, slots=True)
class ScanFinding:
    path: str
    code: str
    detail: str
    severity: str


@dataclass(frozen=True, slots=True)
class SkillScan:
    files: tuple[str, ...]
    scripts: tuple[str, ...]
    assets: tuple[str, ...]
    declared_permissions: tuple[str, ...]
    inferred_permissions: tuple[str, ...]
    findings: tuple[ScanFinding, ...]
    executed_scripts: bool
    malicious: bool


def is_immutable_revision(revision: str) -> bool:
    return bool(_SHA.fullmatch(revision))


def scan_skill_pack(root: Path) -> SkillScan:
    """Read files as data. Do not import, exec, or spawn anything from the pack."""
    files: list[str] = []
    scripts: list[str] = []
    assets: list[str] = []
    findings: list[ScanFinding] = []
    declared: tuple[str, ...] = ()
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        try:
            manifest = load_skill_dir(root)
            declared = manifest.permissions
        except Exception:
            declared = ()
        findings.extend(_reference_escapes(root, skill_md.read_text(encoding="utf-8")))
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files.append(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        is_script = rel.startswith("scripts/") or path.suffix.lower() in _SCRIPT_SUFFIXES
        if is_script:
            scripts.append(rel)
        elif path.name != "SKILL.md":
            assets.append(rel)
        findings.extend(_content_findings(rel, text))
        if path.name == "SKILL.md":
            findings.extend(_reference_escapes(root, text))
    inferred = tuple(sorted({item.code for item in findings if item.code != "eval"}))
    malicious = any(
        item.code in {"network", "secrets", "eval", "path_escape"} for item in findings
    )
    return SkillScan(
        files=tuple(files),
        scripts=tuple(scripts),
        assets=tuple(assets),
        declared_permissions=declared,
        inferred_permissions=inferred,
        findings=tuple(findings),
        executed_scripts=False,
        malicious=malicious,
    )


def _content_findings(rel: str, text: str) -> list[ScanFinding]:
    found: list[ScanFinding] = []
    if _NETWORK.search(text):
        found.append(ScanFinding(rel, "network", "content performs network I/O", "error"))
    if _SECRETS.search(text):
        found.append(ScanFinding(rel, "secrets", "content reads credential-shaped values", "error"))
    if _EVAL.search(text):
        found.append(ScanFinding(rel, "eval", "content evaluates or spawns a shell", "error"))
    if _ESCAPE.search(text):
        found.append(ScanFinding(rel, "path_escape", "content walks outside the pack", "error"))
    return found


def _reference_escapes(root: Path, body: str) -> list[ScanFinding]:
    found: list[ScanFinding] = []
    for match in _REF.finditer(body):
        ref = match.group(1) or match.group(2) or ""
        candidate = ref.split()[0] if ref else ""
        if candidate == "" or re.match(r"^[a-z]+://", candidate, re.I):
            continue
        if _ESCAPE.search(candidate) or _outside(root, candidate):
            found.append(
                ScanFinding("SKILL.md", "path_escape", f"references {candidate}", "error")
            )
    return found


def _outside(root: Path, ref: str) -> bool:
    try:
        resolved = (root / ref).resolve()
    except OSError:
        return True
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return True
    return False


class FixtureSkillSource:
    """Immutable fake revisions mapped to local fixture packs. No network."""

    def __init__(self, packs: Mapping[tuple[str, str], Path]) -> None:
        self._packs = packs

    def fetch(self, locator: str, revision: str) -> Path:
        if not is_immutable_revision(revision):
            raise MutableRevisionError("revision must be an immutable SHA")
        if locator.startswith("http://") or locator.startswith("https://"):
            raise NetworkFetchForbidden("community HTTP fetch is disabled")
        try:
            return Path(self._packs[(locator, revision)])
        except KeyError as error:
            raise FileNotFoundError(locator) from error


class LocalOnlySkillSource:
    def fetch(self, locator: str, revision: str) -> Path:
        if not is_immutable_revision(revision):
            raise MutableRevisionError("revision must be an immutable SHA")
        if locator.startswith("http://") or locator.startswith("https://"):
            raise NetworkFetchForbidden("community HTTP fetch is disabled")
        path = Path(locator)
        if not path.is_dir():
            raise FileNotFoundError(locator)
        return path
