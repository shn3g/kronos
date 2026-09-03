# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded SHA-256 guard against repeated chat tool calls."""

from __future__ import annotations

import hashlib
import json
from collections import deque

from kronos_engine.application.chat_tools import ToolCall


class ToolCallRepeatGuard:
    """Reject exact tool calls already completed successfully in a recent window."""

    def __init__(self, *, window_size: int = 5) -> None:
        if window_size < 1:
            raise ValueError("window size must be positive")
        self._hashes: deque[str] = deque(maxlen=window_size)

    def allow(self, call: ToolCall) -> bool:
        """Return False when this exact call already succeeded recently."""
        return self._fingerprint(call) not in self._hashes

    def remember_success(self, call: ToolCall) -> None:
        """Record a successful tool call so an identical retry is blocked."""
        fingerprint = self._fingerprint(call)
        if fingerprint in self._hashes:
            return
        self._hashes.append(fingerprint)

    def reset(self) -> None:
        self._hashes.clear()

    @staticmethod
    def _fingerprint(call: ToolCall) -> str:
        payload = json.dumps(
            {"arguments": call.arguments, "name": call.name},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
