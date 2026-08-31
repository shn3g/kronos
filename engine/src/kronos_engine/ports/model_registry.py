# SPDX-License-Identifier: AGPL-3.0-or-later
"""Model profile registry port. Application depends on this, not SQL."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from kronos_engine.domain.models import ModelProfile


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    id: str
    kind: str
    display_name: str
    base_url: str | None
    billed: bool
    secret_ref: str
    api_key: None = None


@dataclass(frozen=True, slots=True)
class RoleAssignments:
    planner: str | None
    coder: str | None
    reviewer: str | None
    embedding: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "planner": self.planner,
            "coder": self.coder,
            "reviewer": self.reviewer,
            "embedding": self.embedding,
        }


class ModelRegistry(Protocol):
    def save_provider(self, provider: ProviderConfig) -> None: ...

    def list_providers(self) -> Sequence[ProviderConfig]: ...

    def save_profile(self, profile: ModelProfile) -> None: ...

    def list_profiles(self) -> Sequence[ModelProfile]: ...

    def save_assignments(self, assignments: RoleAssignments) -> None: ...

    def load_assignments(self) -> RoleAssignments: ...
