# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect Cursor/OpenCode CLIs and local OpenAI-compatible endpoints. No repository code."""

from __future__ import annotations

from kronos_engine.adapters.executors.cursor import detect_cursor_cli
from kronos_engine.adapters.executors.opencode import detect_opencode_cli
from kronos_engine.adapters.models.openai_compatible import detect_openai_compatible_endpoints
from kronos_engine.ports.model_provider import DetectedTool


class DefaultToolDetector:
    def detect(self) -> tuple[DetectedTool, ...]:
        found: list[DetectedTool] = []
        cli = detect_cursor_cli()
        if cli is not None:
            found.append(DetectedTool(kind="cursor_cli", label=cli.name, present=True))
        opencode = detect_opencode_cli()
        if opencode is not None:
            found.append(DetectedTool(kind="opencode_cli", label=opencode.name, present=True))
        for endpoint in detect_openai_compatible_endpoints():
            found.append(
                DetectedTool(kind="openai_compatible", label=endpoint.base_url, present=True)
            )
        return tuple(found)
