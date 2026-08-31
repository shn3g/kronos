# SPDX-License-Identifier: AGPL-3.0-or-later
"""Freeze Kronos autonomy. prior wrappers stay as the operator fallback."""

from __future__ import annotations

from dataclasses import dataclass, replace

from kronos_engine.application.repositories import RepositoryService
from kronos_engine.domain.entities import RepositoryId, RepositoryStatus
from kronos_engine.domain.policy import freeze_autonomy as freeze_policy


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    frozen: bool
    wrappers_reenabled: bool
    write_crons_enabled: bool
    fallback: str


def rollback_to_wrappers(repos: RepositoryService, repo_id: RepositoryId) -> RollbackPlan:
    current = repos.get(repo_id)
    frozen = replace(
        current,
        policy=freeze_policy(current.policy),
        status=RepositoryStatus.PAUSED,
    )
    repos.save_policy(frozen)
    return RollbackPlan(
        frozen=True,
        wrappers_reenabled=False,
        write_crons_enabled=False,
        fallback="prior wrappers remain the operator fallback; do not re-enable write crons",
    )
