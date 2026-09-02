# SPDX-License-Identifier: AGPL-3.0-or-later
"""CLI entry for checksums, SBOM, and provenance. Never invents signing keys."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from kronos_engine.ops.release import (
    assert_signed,
    write_checksums,
    write_provenance,
    write_sbom,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kronos release metadata")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--git-sha", default="unknown")
    parser.add_argument("--builder", default="local")
    parser.add_argument("--claim-signed", action="store_true")
    args = parser.parse_args(argv)
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    write_checksums(artifacts)
    write_sbom(
        artifacts / "sbom.cdx.json",
        packages=(
            {"name": "kronos-engine", "version": "0.3.0", "license": "AGPL-3.0-or-later"},
            {"name": "@kronos/desktop", "version": "0.3.0", "license": "AGPL-3.0-or-later"},
        ),
    )
    write_provenance(artifacts / "provenance.json", git_sha=args.git_sha, builder=args.builder)
    signature = artifacts / "release.sig"
    claim = args.claim_signed or os.environ.get("CLAIM_SIGNED", "").strip().lower() == "true"
    signed_path = signature if signature.is_file() else None
    assert_signed(signed_path, claim=claim)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
