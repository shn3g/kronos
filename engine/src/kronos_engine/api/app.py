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
from kronos_engine.adapters.github import GitHubForge
from kronos_engine.adapters.github.client import HttpTransport, HttpxTransport
from kronos_engine.adapters.secrets.os_store import OsSecretStore
from kronos_engine.adapters.tools import DefaultToolDetector
from kronos_engine.api.models import (
    AssignmentsRequest,
    AssignmentsResponse,
    DetectedToolModel,
    EventItem,
    EventListResponse,
    GithubAppRecordResponse,
    GithubAppRegisterRequest,
    GithubAppStatusModel,
    GithubInstallRequest,
    GithubManifestsResponse,
    GithubRulesetRequest,
    GithubStatusResponse,
    GoalListResponse,
    HealthResponse,
    IndexMapResponse,
    IndexSearchHit,
    IndexSearchResponse,
    IndexStatusResponse,
    InspectResponse,
    ModelsSnapshotResponse,
    PathRequest,
    PreviewFileModel,
    ProfileModel,
    ProviderCreateRequest,
    ProviderCreateResponse,
    ProviderModel,
    RepositoryDetailResponse,
    RepositoryListResponse,
    RepositoryRecord,
    VersionResponse,
)
from kronos_engine.application.catalog import CatalogService
from kronos_engine.application.event_query import EventQuery
from kronos_engine.application.github_setup import GitHubSetupService
from kronos_engine.application.model_profiles import (
    ModelProfileService,
    ProviderDraft,
    RoleAssignmentError,
)
from kronos_engine.application.repositories import (
    InspectResult,
    RepositoryNotFound,
    RepositoryService,
)
from kronos_engine.config.repository import EnrolmentPreview, github_owner, render_enrolment_preview
from kronos_engine.config.settings import CLIENT_VERSION_HEADER, Settings, is_loopback_client
from kronos_engine.domain.entities import EnrolledRepository, IdentifierError, RepositoryId
from kronos_engine.domain.github import APP_ROLES
from kronos_engine.domain.models import ModelProfile
from kronos_engine.domain.policy import PolicyError, policy_to_dict
from kronos_engine.domain.version import client_is_compatible
from kronos_engine.indexing.service import IndexingService, IndexStatus
from kronos_engine.ports.forge import (
    ForgeAuthError,
    ForgeTarget,
    GithubAppRecord,
    OperatorConfirmationRequired,
    RulesetWouldWeaken,
)
from kronos_engine.ports.model_provider import ToolDetector
from kronos_engine.ports.model_registry import ProviderConfig
from kronos_engine.ports.repository import RuntimeInsideEnrolledTree
from kronos_engine.ports.secrets import SecretStore
from kronos_engine.state.catalog import SqliteCatalog
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.github_apps import SqliteGithubAppStore
from kronos_engine.state.model_profiles import SqliteModelRegistry
from kronos_engine.state.repositories import SqliteRepositoryRegistry


def create_app(
    settings: Settings,
    database: Database,
    *,
    tool_detector: ToolDetector | None = None,
    secret_store: SecretStore | None = None,
    github_transport: HttpTransport | None = None,
) -> FastAPI:
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

    detector = tool_detector or DefaultToolDetector()
    store = secret_store or OsSecretStore(settings.paths.config)
    github_http = github_transport or HttpxTransport()

    @contextmanager
    def github_service() -> Iterator[GitHubSetupService]:
        conn = database.connect()
        try:
            yield GitHubSetupService(
                SqliteGithubAppStore(conn),
                store,
                github_http,
            )
        finally:
            conn.close()

    @contextmanager
    def model_service() -> Iterator[ModelProfileService]:
        conn = database.connect()
        try:
            yield ModelProfileService(SqliteModelRegistry(conn), store)
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

    @app.get("/models", response_model=ModelsSnapshotResponse)
    def models_snapshot(_: None = Depends(require_auth)) -> ModelsSnapshotResponse:
        with model_service() as service:
            return ModelsSnapshotResponse(
                detected=[
                    DetectedToolModel(kind=item.kind, label=item.label, present=item.present)
                    for item in detector.detect()
                ],
                providers=[_provider_model(item) for item in service.list_providers()],
                profiles=[_profile_model(item) for item in service.list_profiles()],
                assignments=service.assignments().as_dict(),
            )

    @app.post("/models/providers", response_model=ProviderCreateResponse)
    def create_provider(
        body: ProviderCreateRequest, _: None = Depends(require_auth)
    ) -> ProviderCreateResponse:
        with model_service() as service:
            provider = service.register_provider(
                ProviderDraft(
                    kind=body.kind,
                    display_name=body.display_name,
                    base_url=body.base_url,
                    billed=body.billed,
                    api_key=body.api_key,
                )
            )
            profiles = [
                item for item in service.list_profiles() if item.provider_id == provider.id
            ]
            if not profiles:
                raise HTTPException(status_code=500, detail="provider profile was not created")
            coder = next((item for item in profiles if item.role == "coder"), profiles[0])
            return ProviderCreateResponse(
                provider=_provider_model(provider),
                profile=_profile_model(coder),
                profiles=[_profile_model(item) for item in profiles],
            )

    @app.put("/models/assignments", response_model=AssignmentsResponse)
    def assign_models(
        body: AssignmentsRequest, _: None = Depends(require_auth)
    ) -> AssignmentsResponse:
        with model_service() as service:
            try:
                assigned = service.assign(
                    {
                        "planner": body.planner,
                        "coder": body.coder,
                        "reviewer": body.reviewer,
                        "embedding": body.embedding,
                    },
                    confirm_shared_roles=body.confirm_shared_roles,
                )
            except RoleAssignmentError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return AssignmentsResponse(assignments=assigned.as_dict())

    @app.get("/repositories/{repository_id}/index", response_model=IndexStatusResponse)
    def index_status(repository_id: str, _: None = Depends(require_auth)) -> IndexStatusResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            status = IndexingService(settings.paths).status(record.id.value)
            return _index_status(status)

    @app.post("/repositories/{repository_id}/index/rebuild", response_model=IndexStatusResponse)
    def index_rebuild(
        repository_id: str, _: None = Depends(require_auth)
    ) -> IndexStatusResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            status = IndexingService(settings.paths).rebuild(
                record.id.value, Path(record.realpath), record.policy
            )
            return _index_status(status)

    @app.post("/repositories/{repository_id}/index/refresh", response_model=IndexStatusResponse)
    def index_refresh(
        repository_id: str, _: None = Depends(require_auth)
    ) -> IndexStatusResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            status = IndexingService(settings.paths).incremental(
                record.id.value, Path(record.realpath), record.policy
            )
            return _index_status(status)

    @app.get("/repositories/{repository_id}/index/search", response_model=IndexSearchResponse)
    def index_search(
        repository_id: str,
        _: None = Depends(require_auth),
        q: Annotated[str, Query()] = "",
        mode: Annotated[str, Query()] = "hybrid",
    ) -> IndexSearchResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            pack = IndexingService(settings.paths).search(record.id.value, q, mode=mode)
            return IndexSearchResponse(
                items=[
                    IndexSearchHit(
                        path=item.path,
                        start_line=item.start_line,
                        end_line=item.end_line,
                        commit=item.commit,
                        symbol=item.symbol,
                        rank_sources=list(item.rank_sources),
                        trust=item.trust,
                        text=item.text,
                    )
                    for item in pack.items
                ]
            )

    @app.get("/repositories/{repository_id}/index/map", response_model=IndexMapResponse)
    def index_map(repository_id: str, _: None = Depends(require_auth)) -> IndexMapResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            return IndexMapResponse(text=IndexingService(settings.paths).repo_map(record.id.value))

    @app.get("/github/status", response_model=GithubStatusResponse)
    def github_status(_: None = Depends(require_auth)) -> GithubStatusResponse:
        with github_service() as service:
            status = service.status()
            return GithubStatusResponse(
                controller=GithubAppStatusModel(
                    registered=status.controller.registered,
                    installed=status.controller.installed,
                    verified=status.controller.verified,
                ),
                reviewer=GithubAppStatusModel(
                    registered=status.reviewer.registered,
                    installed=status.reviewer.installed,
                    verified=status.reviewer.verified,
                ),
                webhook_enabled=status.webhook_enabled,
                poll_mode=status.poll_mode,
                github_cli_present=status.github_cli_present,
            )

    @app.get("/github/manifests", response_model=GithubManifestsResponse)
    def github_manifests(_: None = Depends(require_auth)) -> GithubManifestsResponse:
        with github_service() as service:
            payload = service.manifests()
            controller = payload["controller"]
            reviewer = payload["reviewer"]
            assert isinstance(controller, dict)
            assert isinstance(reviewer, dict)
            return GithubManifestsResponse(
                controller=controller,
                reviewer=reviewer,
                reviewer_check_name=str(payload["reviewer_check_name"]),
            )

    @app.post("/github/apps/{role}", response_model=GithubAppRecordResponse)
    def github_register_app(
        role: str, body: GithubAppRegisterRequest, _: None = Depends(require_auth)
    ) -> GithubAppRecordResponse:
        if role not in APP_ROLES:
            raise HTTPException(status_code=404, detail="not found")
        if body.gh_token:
            raise HTTPException(status_code=400, detail="GH_TOKEN is not accepted")
        with github_service() as service:
            try:
                record = service.register_app(
                    role=role,
                    app_id=body.app_id,
                    slug=body.slug,
                    private_key=body.private_key,
                )
            except ForgeAuthError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return _github_record(record)

    @app.post("/github/apps/{role}/install", response_model=GithubAppRecordResponse)
    def github_install_app(
        role: str, body: GithubInstallRequest, _: None = Depends(require_auth)
    ) -> GithubAppRecordResponse:
        if role not in APP_ROLES:
            raise HTTPException(status_code=404, detail="not found")
        with github_service() as service:
            try:
                record = service.record_installation(role, body.installation_id)
            except ForgeAuthError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return _github_record(record)

    @app.post("/github/apps/{role}/verify", response_model=GithubAppRecordResponse)
    def github_verify_app(role: str, _: None = Depends(require_auth)) -> GithubAppRecordResponse:
        if role not in APP_ROLES:
            raise HTTPException(status_code=404, detail="not found")
        with github_service() as service:
            try:
                record = service.verify_installation(role)
            except ForgeAuthError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return _github_record(record)

    @app.post("/github/rulesets/propose")
    def github_propose_ruleset(
        body: GithubRulesetRequest, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with github_service() as service:
            try:
                forge = _controller_forge(service, body)
                proposal = forge.propose_ruleset(body.reviewer_integration_id)
            except ForgeAuthError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return {
                "name": proposal.name,
                "strict": proposal.strict,
                "required_checks": [
                    {"context": item.context, "integration_id": item.integration_id}
                    for item in proposal.required_checks
                ],
            }

    @app.post("/github/rulesets/apply")
    def github_apply_ruleset(
        body: GithubRulesetRequest, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with github_service() as service:
            try:
                forge = _controller_forge(service, body)
                proposal = forge.propose_ruleset(body.reviewer_integration_id)
                applied = forge.apply_ruleset(proposal, confirm=body.confirm)
            except OperatorConfirmationRequired as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            except RulesetWouldWeaken as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            except ForgeAuthError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return {"id": applied.id, "strict": applied.strict, "created": applied.created}

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


def _github_record(record: GithubAppRecord) -> GithubAppRecordResponse:
    return GithubAppRecordResponse(
        role=record.role,
        registered=True,
        installed=record.installation_id is not None,
        verified=record.verified,
    )


def _controller_forge(service: GitHubSetupService, body: GithubRulesetRequest) -> GitHubForge:
    return service.forge(
        "controller",
        ForgeTarget(
            owner=body.owner,
            repo=body.repo,
            integration_branch=body.integration_branch,
            protected_branch=body.protected_branch,
        ),
    )


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


def _provider_model(provider: ProviderConfig) -> ProviderModel:
    return ProviderModel(
        id=provider.id,
        kind=provider.kind,
        display_name=provider.display_name,
        base_url=provider.base_url,
        billed=provider.billed,
    )


def _profile_model(profile: ModelProfile) -> ProfileModel:
    return ProfileModel(
        id=profile.id,
        display_name=profile.display_name,
        role=profile.role,
        provider_id=profile.provider_id,
        model_id=profile.model_id,
        billed=profile.billed,
        approved_fallbacks=list(profile.approved_fallbacks),
    )


def _index_status(status: IndexStatus) -> IndexStatusResponse:
    return IndexStatusResponse(
        repository_id=status.repository_id,
        commit=status.commit,
        chunk_count=status.chunk_count,
        dense_available=status.dense_available,
        index_path=status.index_path,
        disk_bytes=status.disk_bytes,
        ready=status.ready,
    )
