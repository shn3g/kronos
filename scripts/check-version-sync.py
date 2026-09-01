# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail if Kronos lockstep version files disagree. Optional Git tag and release notes."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

CLIENT_VERSION_RE = re.compile(r'const CLIENT_VERSION:\s*&str\s*=\s*"([^"]+)"')
DESKTOP_CLIENT_RE = re.compile(r'export const DESKTOP_CLIENT_VERSION\s*=\s*"([^"]+)"')
PY_VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
SBOM_VERSION_RE = re.compile(r'"version":\s*"([^"]+)"')
TAG_VERSION_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")

FALLBACK_NOTES = "Unsigned desktop installers for this tag. Signing is not present."


class VersionReadError(RuntimeError):
    """A lockstep file is missing or does not contain one version."""


def _json_version(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = payload.get("version")
    if not isinstance(value, str) or value.strip() == "":
        raise VersionReadError(f"{path}: missing version")
    return value


def _toml_project_version(path: Path) -> str:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    project = payload.get("project")
    if not isinstance(project, dict):
        raise VersionReadError(f"{path}: missing [project]")
    value = project.get("version")
    if not isinstance(value, str) or value.strip() == "":
        raise VersionReadError(f"{path}: missing version")
    return value


def _toml_package_version(path: Path) -> str:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    package = payload.get("package")
    if not isinstance(package, dict):
        raise VersionReadError(f"{path}: missing [package]")
    value = package.get("version")
    if not isinstance(value, str) or value.strip() == "":
        raise VersionReadError(f"{path}: missing version")
    return value


def _regex_version(path: Path, pattern: re.Pattern[str], label: str) -> str:
    match = pattern.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise VersionReadError(f"{path}: missing {label}")
    return match.group(1)


def _sbom_version(path: Path) -> str:
    found = SBOM_VERSION_RE.findall(path.read_text(encoding="utf-8"))
    unique = set(found)
    if len(unique) != 1:
        raise VersionReadError(f"{path}: mixed or missing SBOM versions {sorted(unique)}")
    return next(iter(unique))


def _client_version(path: Path) -> str:
    return _regex_version(path, CLIENT_VERSION_RE, "CLIENT_VERSION")


def _desktop_client_version(path: Path) -> str:
    return _regex_version(path, DESKTOP_CLIENT_RE, "DESKTOP_CLIENT_VERSION")


def _dunder_version(path: Path) -> str:
    return _regex_version(path, PY_VERSION_RE, "__version__")


LOCKSTEP: tuple[tuple[str, Callable[[Path], str]], ...] = (
    ("package.json", _json_version),
    ("pyproject.toml", _toml_project_version),
    ("apps/desktop/package.json", _json_version),
    ("apps/desktop/src-tauri/tauri.conf.json", _json_version),
    ("apps/desktop/src-tauri/Cargo.toml", _toml_package_version),
    ("apps/desktop/src-tauri/src/engine.rs", _client_version),
    ("apps/desktop/src/api/kronosClient.ts", _desktop_client_version),
    ("engine/pyproject.toml", _toml_project_version),
    ("engine/src/kronos_engine/__init__.py", _dunder_version),
    ("services/reviewer/pyproject.toml", _toml_project_version),
    ("services/reviewer/src/kronos_reviewer/__init__.py", _dunder_version),
    ("engine/src/kronos_engine/ops/release_cli.py", _sbom_version),
)


def read_lockstep_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for relative, reader in LOCKSTEP:
        path = root / relative
        if not path.is_file():
            raise VersionReadError(f"missing lockstep file: {relative}")
        versions[relative] = reader(path)
    return versions


def expected_version_from_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    name = ref.removeprefix("refs/tags/") if ref.startswith("refs/tags/") else ref
    if ref.startswith("refs/") and not ref.startswith("refs/tags/"):
        return None
    match = TAG_VERSION_RE.fullmatch(name)
    if match is None:
        return None
    return match.group(1)


def extract_changelog_section(text: str, version: str) -> str | None:
    marker = f"## [{version}]"
    start = text.find(marker)
    if start < 0:
        return None
    lines = text[start:].splitlines(keepends=True)
    collected: list[str] = []
    for index, line in enumerate(lines):
        if index > 0 and line.startswith("## ["):
            break
        collected.append(line)
    section = "".join(collected).strip()
    return section or None


def _version_from_tag(tag: str) -> str | None:
    name = tag.strip()
    if name.startswith("refs/tags/"):
        name = name.removeprefix("refs/tags/")
    match = TAG_VERSION_RE.fullmatch(name)
    return match.group(1) if match else None


def build_release_notes(changelog: str, version: str) -> str:
    section = extract_changelog_section(changelog, version)
    body = section if section else FALLBACK_NOTES
    downloads = (
        "Download one installer for your OS:\n"
        "\n"
        f"- Windows: Kronos_{version}_x64-setup.exe\n"
        f"- Linux: Kronos_{version}_amd64.deb\n"
        f"- macOS: Kronos_{version}_macos.app.zip\n"
        "\n"
        "Unsigned. Windows SmartScreen and macOS Gatekeeper will warn. Use Run anyway or "
        "right-click Open.\n"
        "\n"
        "Python 3.11+ must be on PATH. Node and Rust are not required to run the installer.\n"
        "\n"
        "SHA256SUMS is optional verification. Source zip/tar.gz is the tree, not the app.\n"
    )
    return f"{body.rstrip()}\n\n{downloads}"


def collect_errors(root: Path, *, github_ref: str | None) -> list[str]:
    errors: list[str] = []
    try:
        versions = read_lockstep_versions(root)
    except VersionReadError as error:
        return [str(error)]
    unique = sorted(set(versions.values()))
    if len(unique) != 1:
        details = ", ".join(f"{path}={version}" for path, version in sorted(versions.items()))
        errors.append(f"lockstep files disagree ({details})")
        product = None
    else:
        product = unique[0]
    expected = expected_version_from_ref(github_ref)
    if expected is not None and product is not None and expected != product:
        errors.append(f"tag v{expected} does not match lockstep version {product}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Kronos lockstep versions")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--write-release-notes")
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.write_release_notes:
        tag = args.tag or os.environ.get("GITHUB_REF_NAME") or os.environ.get("GITHUB_REF") or ""
        version = _version_from_tag(tag)
        if version is None:
            print("tag vX.Y.Z is required for release notes", file=sys.stderr)
            return 1
        changelog_path = root / "CHANGELOG.md"
        changelog = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else ""
        Path(args.write_release_notes).write_text(
            build_release_notes(changelog, version), encoding="utf-8"
        )
        return 0
    errors = collect_errors(root, github_ref=os.environ.get("GITHUB_REF"))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
