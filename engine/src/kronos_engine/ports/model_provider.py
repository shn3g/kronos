# SPDX-License-Identifier: AGPL-3.0-or-later
"""Model completion and local-tool detection ports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from kronos_engine.domain.models import ModelProfile
from kronos_engine.ports.secrets import ScopedSecret


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    profile: ModelProfile
    prompt: str
    fallback_model_id: str | None = None
    fallback_billed: bool = False
    messages: tuple[dict[str, object], ...] | None = None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    tokens: int


@dataclass(frozen=True, slots=True)
class CompletionResult:
    text: str
    usage: TokenUsage


@dataclass(frozen=True, slots=True)
class DetectedTool:
    kind: str
    label: str
    present: bool


class ModelProvider(Protocol):
    def complete(
        self, request: CompletionRequest, secret: ScopedSecret | None
    ) -> CompletionResult: ...


class ToolDetector(Protocol):
    def detect(self) -> Sequence[DetectedTool]: ...
