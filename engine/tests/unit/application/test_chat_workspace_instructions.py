# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from kronos_engine.application.chat_workspace_instructions import (
    MAX_WORKSPACE_INSTRUCTION_CHARS,
    workspace_instruction_text,
)


def test_workspace_instructions_read_root_agents_md_and_skip_nested(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Never commit to main.\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "AGENTS.md").write_text("Nested secret rule.\n", encoding="utf-8")
    text = workspace_instruction_text(tmp_path)
    assert "AGENTS.md" in text
    assert "Never commit to main." in text
    assert "Nested secret rule." not in text


def test_workspace_instructions_attach_cursor_rule_files(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "python.mdc").write_text("Use type hints.\n", encoding="utf-8")
    (tmp_path / ".cursorrules").write_text("No em dashes in UI copy.\n", encoding="utf-8")
    text = workspace_instruction_text(tmp_path)
    assert "No em dashes in UI copy." in text
    assert "Use type hints." in text
    assert ".cursor/rules/python.mdc" in text


def test_workspace_instructions_omit_when_none_exist(tmp_path: Path) -> None:
    assert workspace_instruction_text(tmp_path) == ""


def test_workspace_instructions_skip_nested_cursor_rule_directories(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    nested = rules / "team"
    nested.mkdir(parents=True)
    (nested / "extra.md").write_text("Do not include nested.\n", encoding="utf-8")
    (rules / "root.md").write_text("Keep this.\n", encoding="utf-8")
    text = workspace_instruction_text(tmp_path)
    assert "Keep this." in text
    assert "Do not include nested." not in text


def test_workspace_instructions_cap_size(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("A" * 50_000, encoding="utf-8")
    text = workspace_instruction_text(tmp_path)
    assert text.count("A") <= MAX_WORKSPACE_INSTRUCTION_CHARS
    assert "AGENTS.md" in text
