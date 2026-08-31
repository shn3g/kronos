# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP response models. No business rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


class VersionResponse(BaseModel):
    engine_version: str
    min_client_version: str
    compatible: bool


class RepositoryListResponse(BaseModel):
    repositories: list[dict[str, str]]


class GoalListResponse(BaseModel):
    goals: list[dict[str, str]]


class EventItem(BaseModel):
    seq: int
    id: str
    type: str
    payload: dict[str, Any]
    recorded_at: str


class EventListResponse(BaseModel):
    events: list[EventItem]
    head_seq: int
