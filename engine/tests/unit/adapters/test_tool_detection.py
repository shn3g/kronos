# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect Cursor CLI and local OpenAI-compatible endpoints without running repo code."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.adapters.executors.cursor import detect_cursor_cli
from kronos_engine.adapters.models.openai_compatible import detect_openai_compatible_endpoints


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
