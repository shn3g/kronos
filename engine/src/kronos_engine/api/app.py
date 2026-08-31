# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI composition root. No domain rules live here."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from kronos_engine.api.models import (
    EventItem,
    EventListResponse,
    GoalListResponse,
    HealthResponse,
    RepositoryListResponse,
    VersionResponse,
)
from kronos_engine.application.catalog import Catalog
from kronos_engine.config.settings import CLIENT_VERSION_HEADER, Settings, is_loopback_client
from kronos_engine.domain.version import client_is_compatible
from kronos_engine.state.event_store import SqliteEventStore


def create_app(settings: Settings, conn: sqlite3.Connection) -> FastAPI:
    app = FastAPI(title="Kronos Engine", version=settings.engine_version)
    catalog = Catalog(conn)
    events = SqliteEventStore(conn)

    def require_auth(request: Request) -> None:
        authorization = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.auth_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):  # type: ignore[no-untyped-def]
        host = request.client.host if request.client else ""
        if not is_loopback_client(host):
            return JSONResponse({"detail": "loopback only"}, status_code=403)
        return await call_next(request)

    @app.get("/health", response_model=HealthResponse)
    def health(_: None = Depends(require_auth)) -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/version", response_model=VersionResponse)
    def version(
        _: None = Depends(require_auth),
        x_kronos_client_version: Annotated[str | None, Header(alias=CLIENT_VERSION_HEADER)] = None,
    ) -> VersionResponse:
        client_version = x_kronos_client_version or ""
        compatible = client_is_compatible(
            client_version,
            settings.min_client_version,
            settings.engine_version,
        )
        return VersionResponse(
            engine_version=settings.engine_version,
            min_client_version=settings.min_client_version,
            compatible=compatible,
        )

    @app.get("/repositories", response_model=RepositoryListResponse)
    def repositories(_: None = Depends(require_auth)) -> RepositoryListResponse:
        return RepositoryListResponse(repositories=list(catalog.list_repositories()))

    @app.get("/goals", response_model=GoalListResponse)
    def goals(_: None = Depends(require_auth)) -> GoalListResponse:
        return GoalListResponse(goals=list(catalog.list_goals()))

    @app.get("/events", response_model=EventListResponse)
    def list_events(
        _: None = Depends(require_auth),
        after: Annotated[int, Query()] = 0,
    ) -> EventListResponse:
        stored = events.list_after(after)
        return EventListResponse(
            events=[
                EventItem(
                    seq=item.seq,
                    id=item.id.value,
                    type=item.type,
                    payload=dict(item.payload),
                    recorded_at=item.recorded_at,
                )
                for item in stored
            ],
            head_seq=events.head_seq(),
        )

    return app
