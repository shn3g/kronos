# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect Cursor CLI and local OpenAI-compatible endpoints without running repo code."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kronos_engine.adapters.executors.cursor import detect_cursor_cli
from kronos_engine.adapters.executors.opencode import detect_opencode_cli
from kronos_engine.adapters.models.openai_compatible import detect_openai_compatible_endpoints
from kronos_engine.adapters.tools import DefaultToolDetector


def test_cursor_cli_detection_uses_path_lookup_not_repo_binaries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    decoy = repo / "cursor-agent"
    decoy.write_text("raise SystemExit('pwn')\n", encoding="utf-8")
    found = detect_cursor_cli(
        which=lambda name: (
            str(tmp_path / "safe" / "cursor-agent") if name == "cursor-agent" else None
        )
    )
    assert found is not None
    assert found.name == "cursor-agent"
    assert "repo" not in found.path.replace("\\", "/")
    assert not (repo / "PWNED").exists()


def test_cwd_decoy_cursor_agent_is_not_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    decoy_name = "cursor-agent.exe" if os.name == "nt" else "cursor-agent"
    decoy = cwd / decoy_name
    decoy.write_text("raise SystemExit('pwn')\n", encoding="utf-8")
    if os.name != "nt":
        decoy.chmod(0o755)
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", str(empty_bin))
    found = detect_cursor_cli()
    assert found is None
    assert not (cwd / "PWNED").exists()


def test_cwd_decoy_opencode_is_not_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    decoy_name = "opencode.exe" if os.name == "nt" else "opencode"
    decoy = cwd / decoy_name
    decoy.write_text("raise SystemExit('pwn')\n", encoding="utf-8")
    if os.name != "nt":
        decoy.chmod(0o755)
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", str(empty_bin))
    found = detect_opencode_cli()
    assert found is None
    assert not (cwd / "PWNED").exists()


def test_default_detector_reports_opencode_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / ("opencode.exe" if os.name == "nt" else "opencode")
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if os.name != "nt":
        binary.chmod(0o755)
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", str(bin_dir))
    kinds = {item.kind for item in DefaultToolDetector().detect()}
    assert "opencode_cli" in kinds


def test_openai_compatible_probe_does_not_execute_repository_code(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pwn.py").write_text(
        "from pathlib import Path\nPath('PWNED').write_text('yes')\n",
        encoding="utf-8",
    )

    class Transport:
        def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]:
            _ = timeout
            if url.startswith("http://127.0.0.1:11434/"):
                return 200, {"data": [{"id": "llama3"}]}
            return 599, {}

    found = detect_openai_compatible_endpoints(transport=Transport(), repo_root=repo)
    assert found[0].base_url == "http://127.0.0.1:11434/v1"
    assert found[0].billed is False
    assert "llama3" in found[0].models
    assert not (repo / "PWNED").exists()
    assert not (tmp_path / "PWNED").exists()
