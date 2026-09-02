# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generate latest.json for the Tauri updater from signed bundle artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

WINDOWS_SETUP_RE = re.compile(r".*-setup\.exe$", re.IGNORECASE)
APPIMAGE_RE = re.compile(r".*\.AppImage$", re.IGNORECASE)
MACOS_ARCHIVE_RE = re.compile(r".*\.app\.tar\.gz$", re.IGNORECASE)


class MissingSignatureError(RuntimeError):
    """An updater bundle is present without a matching signature file."""


def extract_changelog_notes(changelog: str, version: str) -> str:
    marker = f"## [{version}]"
    start = changelog.find(marker)
    if start < 0:
        return f"Kronos {version}"
    lines = changelog[start:].splitlines(keepends=True)
    collected: list[str] = []
    for index, line in enumerate(lines):
        if index > 0 and line.startswith("## ["):
            break
        collected.append(line)
    section = "".join(collected).strip()
    return section or f"Kronos {version}"


def platform_key_for_artifact(name: str, *, darwin_arch: str) -> str | None:
    if WINDOWS_SETUP_RE.fullmatch(name):
        return "windows-x86_64"
    if APPIMAGE_RE.fullmatch(name):
        return "linux-x86_64"
    if MACOS_ARCHIVE_RE.fullmatch(name):
        arch = darwin_arch if darwin_arch in {"x86_64", "aarch64"} else "aarch64"
        return f"darwin-{arch}"
    return None


DARWIN_ARCH_MARKER = "darwin-arch.txt"


def resolve_darwin_arch(artifacts_dir: Path, fallback: str) -> str:
    marker = next(
        (path for path in artifacts_dir.rglob(DARWIN_ARCH_MARKER) if path.is_file()),
        None,
    )
    if marker is not None:
        value = marker.read_text(encoding="utf-8").strip()
        if value in {"x86_64", "aarch64"}:
            return value
    return fallback if fallback in {"x86_64", "aarch64"} else "aarch64"


def discover_platforms(
    artifacts_dir: Path,
    *,
    url_builder: Callable[[Path], str],
    darwin_arch: str = "aarch64",
) -> dict[str, dict[str, str]]:
    darwin_arch = resolve_darwin_arch(artifacts_dir, darwin_arch)
    platforms: dict[str, dict[str, str]] = {}
    candidates = sorted(path for path in artifacts_dir.rglob("*") if path.is_file())
    updater_bundles = [
        path
        for path in candidates
        if path.suffix != ".sig" and platform_key_for_artifact(path.name, darwin_arch=darwin_arch)
    ]
    for bundle in updater_bundles:
        signature_path = Path(f"{bundle}.sig")
        if not signature_path.is_file():
            msg = f"missing signature for updater bundle: {bundle}"
            raise MissingSignatureError(msg)
        signature = signature_path.read_text(encoding="utf-8").strip()
        if signature == "":
            msg = f"empty signature: {signature_path}"
            raise MissingSignatureError(msg)
        platform = platform_key_for_artifact(bundle.name, darwin_arch=darwin_arch)
        if platform is None:
            continue
        platforms[platform] = {
            "url": url_builder(bundle),
            "signature": signature,
        }
    if not platforms:
        msg = f"no signed updater artifacts found under {artifacts_dir}"
        raise MissingSignatureError(msg)
    return platforms


def build_latest_json(
    *,
    version: str,
    notes: str,
    platforms: dict[str, dict[str, str]],
    pub_date: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": version,
        "notes": notes,
        "platforms": platforms,
    }
    if pub_date is not None:
        payload["pub_date"] = pub_date
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Tauri updater latest.json")
    parser.add_argument("--artifacts", required=True, help="Bundle output directory")
    parser.add_argument("--version", required=True, help="Release version without leading v")
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--release-base-url", required=True)
    parser.add_argument("--output", default="latest.json")
    parser.add_argument("--darwin-arch", default="aarch64")
    parser.add_argument(
        "--pub-date",
        default=datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    args = parser.parse_args(argv)

    artifacts_dir = Path(args.artifacts)
    if not artifacts_dir.is_dir():
        print(f"artifacts directory not found: {artifacts_dir}", file=sys.stderr)
        return 1

    changelog_path = Path(args.changelog)
    changelog = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else ""
    notes = extract_changelog_notes(changelog, args.version)
    base = args.release_base_url.rstrip("/")

    def url_builder(path: Path) -> str:
        return f"{base}/{path.name}"

    try:
        platforms = discover_platforms(
            artifacts_dir,
            url_builder=url_builder,
            darwin_arch=args.darwin_arch,
        )
    except MissingSignatureError as error:
        print(str(error), file=sys.stderr)
        return 1

    payload = build_latest_json(
        version=args.version,
        notes=notes,
        platforms=platforms,
        pub_date=args.pub_date,
    )
    output = Path(args.output)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
