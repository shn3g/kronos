# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse fenced tool calls from model text. No I/O."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

TOOL_FENCE = re.compile(r"```tool\s*(\{.*?\})\s*```", re.DOTALL)

ALLOWED_TOOLS = frozenset(
    {
        "search_index",
        "list_files",
        "read_file",
        "write_file",
        "configure_model",
        "create_goal",
        "list_goals",
        "search_memory",
        "run_command",
    }
)


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, object]


class ToolParseError(ValueError):
    """Raised when a tool fence is present but not usable."""


def parse_tool_call(text: str) -> ToolCall | None:
    match = TOOL_FENCE.search(text)
    if match is None:
        return None
    try:
        payload: Any = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise ToolParseError("tool call is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ToolParseError("tool call must be an object")
    name = payload.get("name")
    if not isinstance(name, str) or name not in ALLOWED_TOOLS:
        raise ToolParseError("unknown tool")
    arguments: dict[str, object] = {}
    for key, value in payload.items():
        if key == "name":
            continue
        arguments[key] = value
    return ToolCall(name=name, arguments=arguments)


def strip_tool_fence(text: str) -> str:
    return TOOL_FENCE.sub("", text).strip()


def redact_tool_arguments(arguments: dict[str, object]) -> dict[str, object]:
    """Return tool arguments safe to retain in conversation history."""
    return {
        key: "[REDACTED]" if key.casefold() in {"api_key", "apikey"} else value
        for key, value in arguments.items()
    }
