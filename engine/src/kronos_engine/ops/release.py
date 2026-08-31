# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checksums, SBOM, and provenance. Signed assertions fail closed without keys."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path


class UnsignedReleaseError(RuntimeError):
    """Raised when a signed assertion is made without a signature or key."""


def write_checksums(artifact_dir: Path) -> Path:
    skip = {"SHA256SUMS", "sbom.cdx.json", "provenance.json"}
    lines: list[str] = []
    for path in sorted(p for p in artifact_dir.rglob("*") if p.is_file()):
        if path.name in skip:
            continue
        rel = path.relative_to(artifact_dir).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    output = artifact_dir / "SHA256SUMS"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def write_sbom(output: Path, *, packages: Sequence[Mapping[str, str]]) -> Path:
    components = []
    for package in packages:
        components.append(
            {
                "type": "library",
                "name": package["name"],
                "version": package["version"],
                "licenses": [{"license": {"id": package.get("license", "AGPL-3.0-or-later")}}],
            }
        )
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": components,
    }
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return output


def write_provenance(output: Path, *, git_sha: str, builder: str) -> Path:
    document = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://kronos.local/release@v1",
                "resolvedDependencies": [],
            },
            "runDetails": {
                "builder": {"id": builder},
                "metadata": {"revision": git_sha},
            },
        },
        "subject": [{"name": "kronos", "digest": {"gitCommit": git_sha}}],
    }
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return output


def assert_signed(signature: Path | None, *, claim: bool) -> None:
    if not claim:
        return None
    if signature is None or not Path(signature).is_file():
        raise UnsignedReleaseError("signed assertion failed: no signing key")
    return None

