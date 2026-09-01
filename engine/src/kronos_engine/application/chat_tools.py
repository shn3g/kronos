# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse fenced tool calls from model text. No I/O."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

TOOL_FENCE = re.compile(r"```tool\s*(\{.*?\})\s*```", re.DOTALL)

ALLOWED_TOOLS = frozenset(
    {"search_index", "read_file", "write_file", "create_goal", "list_goals", "search_memory"}
)


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, str]


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
    arguments: dict[str, str] = {}
    for key, value in payload.items():
        if key == "name":
            continue
        if isinstance(value, str):
            arguments[key] = value
        elif value is not None:
            arguments[key] = str(value)
    return ToolCall(name=name, arguments=arguments)


def strip_tool_fence(text: str) -> str:
    return TOOL_FENCE.sub("", text).strip()
