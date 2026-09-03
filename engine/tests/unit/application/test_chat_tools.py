# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from kronos_engine.application.chat_tools import (
    ALLOWED_TOOLS,
    ToolParseError,
    parse_tool_call,
    strip_tool_fence,
)


def test_parse_tool_call_reads_fenced_json() -> None:
    text = 'I will search.\n```tool\n{"name": "search_index", "query": "onboarding"}\n```\n'
    call = parse_tool_call(text)
    assert call is not None
    assert call.name == "search_index"
    assert call.arguments["query"] == "onboarding"
    assert "search_index" not in strip_tool_fence(text)


def test_parse_tool_call_returns_none_for_plain_replies() -> None:
    assert parse_tool_call("Staff is missing before the calendar route.") is None


def test_parse_tool_call_rejects_unknown_tools() -> None:
    with pytest.raises(ToolParseError, match="unknown tool"):
        parse_tool_call('```tool\n{"name": "rm_rf", "path": "/"}\n```')


def test_parse_tool_call_allows_write_file_and_search_memory() -> None:
    write = parse_tool_call(
        '```tool\n{"name": "write_file", "path": "src/a.py", "content": "x = 1\\n"}\n```'
    )
    assert write is not None
    assert write.name == "write_file"
    assert write.arguments["path"] == "src/a.py"
    memory = parse_tool_call('```tool\n{"name": "search_memory", "query": "staff guard"}\n```')
    assert memory is not None
    assert memory.name == "search_memory"


def test_parse_tool_call_allows_run_command() -> None:
    call = parse_tool_call('```tool\n{"name": "run_command", "command": "python probe.py"}\n```')
    assert call is not None
    assert call.name == "run_command"
    assert call.arguments["command"] == "python probe.py"


def test_parse_tool_call_allows_list_files() -> None:
    assert "list_files" in ALLOWED_TOOLS
    call = parse_tool_call('```tool\n{"name": "list_files", "glob": "src/**/*.py"}\n```')
    assert call is not None
    assert call.name == "list_files"
    assert call.arguments["glob"] == "src/**/*.py"
    bare = parse_tool_call('```tool\n{"name": "list_files"}\n```')
    assert bare is not None
    assert bare.name == "list_files"


def test_parse_tool_call_preserves_configure_model_roles() -> None:
    call = parse_tool_call(
        """```tool
{"name": "configure_model", "provider": "openai_compatible",
 "model": "gpt-4.1-mini", "roles": ["orchestrator", "coder"]}
```"""
    )
    assert call is not None
    assert call.name == "configure_model"
    assert call.arguments["provider"] == "openai_compatible"
    assert call.arguments["roles"] == ["orchestrator", "coder"]
