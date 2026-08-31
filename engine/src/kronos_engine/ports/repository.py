# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repository registry and git inspector ports. Application depends on these."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from kronos_engine.domain.entities import EnrolledRepository, RepositoryId


class RepositoryRegistry(Protocol):
    def get(self, repo_id: RepositoryId) -> EnrolledRepository | None: ...

    def get_by_realpath(self, realpath: str) -> EnrolledRepository | None: ...

    def list(self) -> Sequence[EnrolledRepository]: ...

    def save(self, repo: EnrolledRepository) -> None: ...

    def delete(self, repo_id: RepositoryId) -> None: ...
