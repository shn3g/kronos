# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer is separately packaged and does not import engine adapters."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "kronos_reviewer"
PYPROJECT = ROOT / "pyproject.toml"


def test_reviewer_sources_do_not_import_engine_adapters() -> None:
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "kronos_engine.adapters" not in text, path


def test_reviewer_pyproject_declares_httpx_and_engine_domain_dep() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "httpx" in text
    assert "kronos-engine" in text
    assert "../../engine/src" not in text
