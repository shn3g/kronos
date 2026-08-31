# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI composition root. No domain rules live here."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector, GitError
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.api.models import (
    EventItem,
    EventListResponse,
    GoalListResponse,
    HealthResponse,
    InspectResponse,
    PathRequest,
    PreviewFileModel,
    RepositoryDetailResponse,
    RepositoryListResponse,
    RepositoryRecord,
    VersionResponse,
)
from kronos_engine.application.catalog import CatalogService
from kronos_engine.application.event_query import EventQuery
from kronos_engine.application.repositories import (
    InspectResult,
    RepositoryNotFound,
    RepositoryService,
)
from kronos_engine.config.repository import EnrolmentPreview, github_owner, render_enrolment_preview
from kronos_engine.config.settings import CLIENT_VERSION_HEADER, Settings, is_loopback_client
from kronos_engine.domain.entities import EnrolledRepository, IdentifierError, RepositoryId
from kronos_engine.domain.policy import PolicyError, policy_to_dict
from kronos_engine.domain.version import client_is_compatible
from kronos_engine.ports.repository import RuntimeInsideEnrolledTree
from kronos_engine.state.catalog import SqliteCatalog
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.repositories import SqliteRepositoryRegistry


def create_app(settings: Settings, database: Database) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(title="Kronos Engine", version=settings.engine_version, lifespan=lifespan)

    def require_auth(request: Request) -> None:
        authorization = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.auth_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="unauthorized")

    @contextmanager
    def catalog_service() -> Iterator[CatalogService]:
        conn = database.connect()
        try:
            yield CatalogService(SqliteCatalog(conn))
        finally:
            conn.close()

    @contextmanager
    def event_query() -> Iterator[EventQuery]:
        conn = database.connect()
        try:
            yield EventQuery(SqliteEventStore(conn))
        finally:
            conn.close()

    @contextmanager
    def repository_service() -> Iterator[RepositoryService]:
        conn = database.connect()
        try:
            yield RepositoryService(
                SqliteRepositoryRegistry(conn),
                settings.paths,
                FilesystemGitInspector(),
                ManifestStackDetector(),
                CacheRuntimeLayout(),
            )
        finally:
            conn.close()

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
        with repository_service() as service:
            return RepositoryListResponse(
                repositories=[_repository_record(item) for item in service.list()]
            )

    @app.post("/repositories/inspect", response_model=InspectResponse)
    def inspect_repository(
        body: PathRequest, _: None = Depends(require_auth)
    ) -> InspectResponse:
        with repository_service() as service:
            try:
                result = service.inspect(body.path)
            except GitError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return _inspect_response(result)

    @app.post("/repositories", response_model=RepositoryDetailResponse)
    def enrol_repository(
        body: PathRequest, _: None = Depends(require_auth)
    ) -> RepositoryDetailResponse:
        with repository_service() as service:
            try:
                record = service.enrol(body.path, body.policy)
            except (GitError, PolicyError, RuntimeInsideEnrolledTree) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return _detail_response(service, record, include_preview=True)

    @app.get("/repositories/{repository_id}", response_model=RepositoryDetailResponse)
    def get_repository(
        repository_id: str, _: None = Depends(require_auth)
    ) -> RepositoryDetailResponse:
        with repository_service() as service:
            record = _load(service, repository_id)
            return _detail_response(service, record)

    @app.get("/repositories/{repository_id}/preview", response_model=InspectResponse)
    def preview_repository(
        repository_id: str, _: None = Depends(require_auth)
    ) -> InspectResponse:
        with repository_service() as service:
            record = _load(service, repository_id)
            try:
                result = service.preview(record.id)
            except GitError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return _inspect_response(result)

    @app.post("/repositories/{repository_id}/pause", response_model=RepositoryDetailResponse)
    def pause_repository(
        repository_id: str, _: None = Depends(require_auth)
    ) -> RepositoryDetailResponse:
        with repository_service() as service:
            try:
                record = service.pause(_parse_id(repository_id))
            except (RepositoryNotFound, IdentifierError) as error:
                raise HTTPException(status_code=404, detail="not found") from error
            return _detail_response(service, record)

    @app.post("/repositories/{repository_id}/disable", response_model=RepositoryDetailResponse)
    def disable_repository(
        repository_id: str, _: None = Depends(require_auth)
    ) -> RepositoryDetailResponse:
        with repository_service() as service:
            try:
                record = service.disable(_parse_id(repository_id))
            except (RepositoryNotFound, IdentifierError) as error:
                raise HTTPException(status_code=404, detail="not found") from error
            return _detail_response(service, record)

    @app.post("/repositories/{repository_id}/resume", response_model=RepositoryDetailResponse)
    def resume_repository(
        repository_id: str, _: None = Depends(require_auth)
    ) -> RepositoryDetailResponse:
        with repository_service() as service:
            try:
                record = service.resume(_parse_id(repository_id))
            except (RepositoryNotFound, IdentifierError) as error:
                raise HTTPException(status_code=404, detail="not found") from error
            return _detail_response(service, record)

    @app.post("/repositories/{repository_id}/remove")
    def remove_repository(repository_id: str, _: None = Depends(require_auth)) -> dict[str, bool]:
        with repository_service() as service:
            try:
                service.remove(_parse_id(repository_id))
            except (RepositoryNotFound, IdentifierError) as error:
                raise HTTPException(status_code=404, detail="not found") from error
            return {"removed": True}

    @app.post("/repositories/{repository_id}/re-enrol", response_model=RepositoryDetailResponse)
    def reenrol_repository(
        repository_id: str,
        _: None = Depends(require_auth),
        redetect: Annotated[bool, Query()] = False,
    ) -> RepositoryDetailResponse:
        with repository_service() as service:
            try:
                record = service.reenrol(repo_id=_parse_id(repository_id), redetect=redetect)
            except (RepositoryNotFound, IdentifierError, GitError) as error:
                status = 404 if isinstance(error, (RepositoryNotFound, IdentifierError)) else 400
                raise HTTPException(status_code=status, detail=str(error)) from error
            return _detail_response(service, record, include_preview=True)

    @app.get("/goals", response_model=GoalListResponse)
    def goals(_: None = Depends(require_auth)) -> GoalListResponse:
        with catalog_service() as catalog:
            return GoalListResponse(
                goals=[
                    {"id": goal.id.value, "repository_id": goal.repository_id.value}
                    for goal in catalog.list_goals()
                ]
            )

    @app.get("/events", response_model=EventListResponse)
    def list_events(
        _: None = Depends(require_auth),
        after: Annotated[int, Query()] = 0,
    ) -> EventListResponse:
        with event_query() as events:
            stored, head_seq = events.list_after(after)
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
                head_seq=head_seq,
            )

    return app


def _parse_id(repository_id: str) -> RepositoryId:
    try:
        return RepositoryId(repository_id)
    except IdentifierError as error:
        raise HTTPException(status_code=404, detail="not found") from error


def _load(service: RepositoryService, repository_id: str) -> EnrolledRepository:
    try:
        return service.get(_parse_id(repository_id))
    except RepositoryNotFound as error:
        raise HTTPException(status_code=404, detail="not found") from error


def _repository_record(repo: EnrolledRepository) -> RepositoryRecord:
    return RepositoryRecord(
        id=repo.id.value,
        display_name=repo.display_name,
        realpath=repo.realpath,
        origin=repo.origin,
        status=repo.status.value,
    )


def _preview_models(preview: EnrolmentPreview) -> list[PreviewFileModel]:
    return [
        PreviewFileModel(
            path=item.path,
            action=item.action,
            content=item.content,
            unified_diff=item.unified_diff,
        )
        for item in preview.files
    ]


def _inspect_response(result: InspectResult) -> InspectResponse:
    preview = result.preview
    files = _preview_models(preview) if isinstance(preview, EnrolmentPreview) else []
    return InspectResponse(
        git_root=result.git_root,
        origin=result.origin,
        current_branch=result.current_branch,
        default_branch=result.default_branch,
        languages=list(result.languages),
        package_managers=list(result.package_managers),
        policy=policy_to_dict(result.policy),
        preview=files,
        wrote_files=False,
        committed=False,
        pushed=False,
    )


def _detail_response(
    service: RepositoryService,
    record: EnrolledRepository,
    *,
    include_preview: bool = False,
) -> RepositoryDetailResponse:
    runtime = service.runtime_paths(record.id)
    preview = None
    if include_preview:
        preview = _preview_models(
            render_enrolment_preview(
                Path(record.realpath),
                record.policy,
                github_owner(record.origin),
            )
        )
    return RepositoryDetailResponse(
        repository=_repository_record(record),
        policy=policy_to_dict(record.policy),
        runtime={"state_dir": runtime.state_dir, "worktrees": runtime.worktrees},
        preview=preview,
        wrote_files=False,
        committed=False,
        pushed=False,
    )
