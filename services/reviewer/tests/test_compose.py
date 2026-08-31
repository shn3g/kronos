# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compose isolates reviewer filesystem and credentials from the engine."""

from __future__ import annotations

from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[3] / "deploy" / "compose.yaml"


def _block(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None
    chunks: list[str] = []
    for line in lines:
        if start is None:
            if line.startswith(f"  {heading}:"):
                start = line
            continue
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            break
        chunks.append(line)
    assert start is not None, f"missing service {heading}"
    return "\n".join(chunks)


def test_compose_runs_reviewer_with_isolated_mounts_and_credentials() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    engine = _block(text, "engine")
    reviewer = _block(text, "reviewer")
    assert "reviewer-data" in reviewer
    assert "reviewer-sandbox" in reviewer
    assert "engine-data" in engine
    assert "reviewer-data" not in engine
    assert "engine-data" not in reviewer
    assert "reviewer_private_key" in reviewer
    assert "reviewer_attestation_key" in reviewer
    assert "controller_private_key" not in reviewer
    assert "reviewer_private_key" not in engine
    assert "reviewer_attestation_key" not in engine
    assert "GH_TOKEN" not in reviewer or 'GH_TOKEN: ""' in reviewer or "GH_TOKEN:" not in reviewer
    assert "kronos-review (kronos-reviewer)" in text
    assert "hermes" not in text.lower()
