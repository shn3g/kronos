# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI composition root. No domain rules live here."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector, GitError
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.adapters.github import GitHubForge
from kronos_engine.adapters.github.client import HttpTransport, HttpxTransport
from kronos_engine.adapters.secrets.os_store import OsSecretStore, SecretStoreError
from kronos_engine.adapters.tools import DefaultToolDetector
from kronos_engine.api.models import (
    AssignmentsRequest,
    AssignmentsResponse,
    BackupRequest,
    DetectedToolModel,
    EmbeddingBackendModel,
    EventItem,
    EventListResponse,
    GithubAppRecordResponse,
    GithubAppStatusModel,
    GithubEnrolledModel,
    GithubInstallRequest,
    GithubManifestConvertRequest,
    GithubManifestsResponse,
    GithubRulesetRequest,
    GithubStatusResponse,
    GoalCreateRequest,
    GoalDetailResponse,
    GoalIngestRequest,
    GoalListResponse,
    GoalModel,
    GoalTickResponse,
    HealthResponse,
    IndexMapResponse,
    IndexSearchHit,
    IndexSearchResponse,
    IndexStatusResponse,
    IndexWatchRequest,
    InspectResponse,
    LessonImportRequest,
    ModelsSnapshotResponse,
    OpsSettingsRequest,
    PathRequest,
    PreviewFileModel,
    ProfileModel,
    ProviderCreateRequest,
    ProviderCreateResponse,
    ProviderModel,
    RepositoryDetailResponse,
    RepositoryListResponse,
    RepositoryRecord,
    RunListResponse,
    RunModel,
    SkillApproveRequest,
    SkillImportRequest,
    SkillRouteRequest,
    TaskModel,
    TelegramAllowlistRequest,
    TelegramStatusResponse,
    TelegramTokenRequest,
    VersionResponse,
)
from kronos_engine.application.composition import build_goal_engine
from kronos_engine.application.doctor import DoctorService, OpsSettings
from kronos_engine.application.embeddings import ResolvedEmbedder, resolve_embedder
from kronos_engine.application.event_query import EventQuery
from kronos_engine.application.github_setup import GitHubSetupService
from kronos_engine.application.goal_engine import GoalEngine
from kronos_engine.application.goals import GoalService
from kronos_engine.application.model_profiles import (
    ModelProfileService,
    ProviderDraft,
    RoleAssignmentError,
)
from kronos_engine.application.notifications import NotificationService
from kronos_engine.application.planning import Planner
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import (
    InspectResult,
    RepositoryNotFound,
    RepositoryService,
)
from kronos_engine.application.verification import GateRunner
from kronos_engine.config.repository import (
    EnrolmentPreview,
    github_owner,
    github_owner_repo,
    render_enrolment_preview,
)
from kronos_engine.config.settings import CLIENT_VERSION_HEADER, Settings, is_loopback_client
from kronos_engine.domain.budgets import BreakerTripped, BudgetExceeded
from kronos_engine.domain.entities import EnrolledRepository, GoalId, IdentifierError, RepositoryId
from kronos_engine.domain.github import APP_ROLES
from kronos_engine.domain.goals import (
    GoalRecord,
    GoalSource,
    GoalSpec,
    GoalValidationError,
    InvalidTransition,
)
from kronos_engine.domain.models import ModelProfile
from kronos_engine.domain.policy import PolicyError, policy_to_dict
from kronos_engine.domain.tasks import SchemaError, WipExceeded
from kronos_engine.domain.version import client_is_compatible
from kronos_engine.domain.workflow import UnresolvedEvidence
from kronos_engine.indexing.service import IndexingService, IndexStatus
from kronos_engine.indexing.watcher import IndexWatcher
from kronos_engine.memory.procedural import backfill_memory_vectors
from kronos_engine.memory.promotion import PromotionBlocked, activate_promoted
from kronos_engine.memory.records import MemoryRecord, MemoryRejected
from kronos_engine.observability.otel import LocalMetrics, Tracer
from kronos_engine.ports.executor import Executor
from kronos_engine.ports.forge import (
    ForgeAuthError,
    ForgeTarget,
    ForgeTransientError,
    GithubAppRecord,
    GithubAppStatus,
    OperatorConfirmationRequired,
    RulesetWouldWeaken,
)
from kronos_engine.ports.model_provider import ToolDetector
from kronos_engine.ports.model_registry import ProviderConfig
from kronos_engine.ports.repository import RuntimeInsideEnrolledTree
from kronos_engine.ports.secrets import SecretStore
from kronos_engine.skills.catalog import (
    HumanApprovalRequired,
    SkillCatalog,
    bundled_skills_root,
    skill_to_dict,
)
from kronos_engine.skills.evaluation import evaluate_skill
from kronos_engine.skills.quarantine import (
    MutableRevisionError,
    NetworkFetchForbidden,
    SkillSourcePort,
    SkillStillQuarantined,
)
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.github_apps import SqliteGithubAppStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.model_profiles import SqliteModelRegistry
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry
from kronos_engine.state.telegram import SqliteTelegramStore
from kronos_engine.telegram.auth import BOT_TOKEN_REF, BOTFATHER_STEPS, BOTFATHER_URL
from kronos_engine.telegram.client import (
    HttpxTelegramTransport,
    TelegramBotClient,
    TelegramTransport,
)
from kronos_engine.telegram.commands import TelegramConnector
from kronos_engine.telegram.poller import TelegramPoller


def create_app(
    settings: Settings,
    database: Database,
    *,
    tool_detector: ToolDetector | None = None,
    secret_store: SecretStore | None = None,
    github_transport: HttpTransport | None = None,
    planner: Planner | None = None,
    executor: Executor | None = None,
    gates: GateRunner | None = None,
    goal_forge: object | None = None,
    skills_root: Path | None = None,
    skill_source: SkillSourcePort | None = None,
    telegram_transport: TelegramTransport | None = None,
    telegram_auto_poll: bool = False,
) -> FastAPI:
    embedding_startup: list[Callable[[], None]] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        for hook in embedding_startup:
            hook()
        stop_polling = threading.Event()
        worker: threading.Thread | None = None
        watcher: IndexWatcher | None = None
        try:
            watcher = IndexWatcher(
                list_repos=_list_watched_repos,
                indexer_factory=_live_indexer,
            )
            watcher.start()
        except Exception:
            logging.getLogger("kronos.engine").exception("index watcher failed to start")
            watcher = None
        _app.state.index_watcher = watcher
        if telegram_auto_poll:
            poller = TelegramPoller(store, telegram_connector)

            def _poll() -> None:
                while not stop_polling.wait(1.5):
                    poller.tick()

            worker = threading.Thread(target=_poll, daemon=True, name="kronos-telegram")
            worker.start()
        yield
        stop_polling.set()
        if worker is not None:
            worker.join(timeout=2.0)
        if watcher is not None:
            watcher.stop()

    app = FastAPI(title="Kronos Engine", version=settings.engine_version, lifespan=lifespan)

    def require_auth(request: Request) -> None:
        authorization = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.auth_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="unauthorized")

    @contextmanager
    def event_query() -> Iterator[EventQuery]:
        conn = database.connect()
        try:
            yield EventQuery(SqliteEventStore(conn))
        finally:
            conn.close()

    @contextmanager
    def recorder() -> Iterator[Recorder]:
        conn = database.connect()
        try:
            yield Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn))
        finally:
            conn.close()

    @contextmanager
    def goal_service() -> Iterator[GoalService]:
        conn = database.connect()
        try:
            repos = RepositoryService(
                SqliteRepositoryRegistry(conn),
                settings.paths,
                FilesystemGitInspector(),
                ManifestStackDetector(),
                CacheRuntimeLayout(),
            )
            yield GoalService(
                SqliteGoalStore(conn),
                repos,
                Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)),
                notifications=_notifications_for(conn),
            )
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
                indexer=_indexing_service(conn),
            )
        finally:
            conn.close()

    detector = tool_detector or DefaultToolDetector()
    store = secret_store or OsSecretStore(settings.paths.config)
    github_http = github_transport or HttpxTransport()

    def _resolve_embedder(conn: object) -> ResolvedEmbedder:
        return resolve_embedder(
            SqliteModelRegistry(conn),  # type: ignore[arg-type]
            store,
            settings.paths.cache / "models",
        )

    def _emit_index_event(kind: str, payload: Mapping[str, object]) -> None:
        try:
            conn = database.connect()
            try:
                Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)).emit(kind, payload)
            finally:
                conn.close()
        except Exception:
            logging.getLogger("kronos.engine").exception("index event emit failed")

    def _indexing_service(conn: object) -> IndexingService:
        return IndexingService(
            settings.paths,
            embeddings=_resolve_embedder(conn).adapter,
            emit_event=_emit_index_event,
        )

    def _current_embedder() -> ResolvedEmbedder:
        conn = database.connect()
        try:
            return _resolve_embedder(conn)
        finally:
            conn.close()

    def _live_indexer() -> IndexingService:
        return IndexingService(
            settings.paths,
            embeddings=_current_embedder().adapter,
            emit_event=_emit_index_event,
        )

    def _list_watched_repos() -> tuple[EnrolledRepository, ...]:
        conn = database.connect()
        try:
            return tuple(SqliteRepositoryRegistry(conn).list())
        except Exception:
            logging.getLogger("kronos.engine").exception("index watch list failed")
            return ()
        finally:
            conn.close()

    def _warm_embeddings() -> None:
        try:
            conn = database.connect()
            try:
                backfill_memory_vectors(conn, _resolve_embedder(conn).adapter)
            finally:
                conn.close()
        except Exception:
            logging.getLogger("kronos.engine").exception("memory embedding backfill failed")

    embedding_startup.append(_warm_embeddings)

    def _ops_flags() -> OpsSettings:
        conn = database.connect()
        try:
            return DoctorService(
                conn,
                settings,
                store,
                Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)),
            ).settings()
        finally:
            conn.close()

    ops_flags = _ops_flags()
    metrics = LocalMetrics()
    tracer = Tracer(
        destination=settings.paths.logs / "spans.jsonl",
        export_sink=settings.paths.logs / "otel-export.jsonl",
        otel_export=ops_flags.otel_export,
        langfuse_export=ops_flags.langfuse_export,
    )
    app.state.metrics = metrics
    app.state.tracer = tracer

    @contextmanager
    def goal_engine() -> Iterator[GoalEngine]:
        conn = database.connect()
        try:
            yield build_goal_engine(
                conn,
                settings,
                store,
                github_http,
                planner=planner,
                executor=executor,
                gates=gates,
                forge=goal_forge,
                notifications=_notifications_for(conn),
            )
        finally:
            conn.close()

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

    chosen_skills_root = skills_root or bundled_skills_root()

    @contextmanager
    def skill_catalog() -> Iterator[SkillCatalog]:
        conn = database.connect()
        try:
            catalog = SkillCatalog(
                conn,
                skills_root=chosen_skills_root,
                store_dir=settings.paths.cache / "skills",
                source=skill_source,
                embeddings=_resolve_embedder(conn).adapter,
            )
            catalog.load_core()
            yield catalog
        finally:
            conn.close()

    class _NullTelegramTransport:
        def get_updates(self, offset: int, timeout: int = 0) -> list[object]:
            _ = offset, timeout
            return []

        def send_message(self, chat_id: int, text: str) -> None:
            _ = chat_id, text

    def _bot_token() -> str | None:
        try:
            return store.get(BOT_TOKEN_REF)
        except SecretStoreError:
            return None

    def _telegram_transport_for(token: str | None) -> TelegramTransport:
        if telegram_transport is not None:
            return telegram_transport
        if token:
            return HttpxTelegramTransport(token)
        return _NullTelegramTransport()

    def _notifications_for(conn: object) -> NotificationService:
        telegram_store = SqliteTelegramStore(conn)  # type: ignore[arg-type]
        client = TelegramBotClient(store, _telegram_transport_for(_bot_token()))
        return NotificationService(client, telegram_store)

    @contextmanager
    def telegram_connector() -> Iterator[TelegramConnector]:
        conn = database.connect()
        try:
            repos = RepositoryService(
                SqliteRepositoryRegistry(conn),
                settings.paths,
                FilesystemGitInspector(),
                ManifestStackDetector(),
                CacheRuntimeLayout(),
            )
            telegram_store = SqliteTelegramStore(conn)
            client = TelegramBotClient(store, _telegram_transport_for(_bot_token()))
            notifications = NotificationService(client, telegram_store)
            goals = GoalService(
                SqliteGoalStore(conn),
                repos,
                Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)),
                notifications=notifications,
            )
            yield TelegramConnector(
                client=client,
                store=telegram_store,
                secrets=store,
                goals=goals,
                repos=repos,
                notifications=notifications,
            )
        finally:
            conn.close()

    @contextmanager
    def doctor_service() -> Iterator[DoctorService]:
        conn = database.connect()
        try:
            yield DoctorService(
                conn,
                settings,
                store,
                Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)),
            )
        finally:
            conn.close()

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):  # type: ignore[no-untyped-def]
        host = request.client.host if request.client else ""
        if not is_loopback_client(host):
            return JSONResponse({"detail": "loopback only"}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def observe_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        counts = getattr(request.app.state, "metrics", None)
        active = getattr(request.app.state, "tracer", None)
        if isinstance(counts, LocalMetrics):
            counts.inc("http.requests")
        if not isinstance(active, Tracer):
            return await call_next(request)
        with active.span(request.url.path, {"method": request.method}):
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
                embedding_backend=_embedding_backend_model(_current_embedder()),
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
            status = _live_indexer().status(record.id.value, policy=record.policy)
            return _index_status(status)

    @app.post("/repositories/{repository_id}/index/rebuild", response_model=IndexStatusResponse)
    def index_rebuild(
        repository_id: str, _: None = Depends(require_auth)
    ) -> IndexStatusResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            status = _live_indexer().rebuild(
                record.id.value, Path(record.realpath), record.policy
            )
            return _index_status(status)

    @app.post("/repositories/{repository_id}/index/refresh", response_model=IndexStatusResponse)
    def index_refresh(
        repository_id: str, _: None = Depends(require_auth)
    ) -> IndexStatusResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            status = _live_indexer().incremental(
                record.id.value, Path(record.realpath), record.policy
            )
            return _index_status(status)

    @app.post("/repositories/{repository_id}/index/watch", response_model=IndexStatusResponse)
    def index_watch(
        repository_id: str,
        body: IndexWatchRequest,
        _: None = Depends(require_auth),
    ) -> IndexStatusResponse:
        with repository_service() as repos:
            record = _load(repos, repository_id)
            status = _live_indexer().set_watch_enabled(
                record.id.value, body.enabled, policy=record.policy
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
            pack = _live_indexer().search(record.id.value, q, mode=mode)
            with recorder() as events:
                events.emit(
                    "retrieval.searched",
                    {"repository_id": record.id.value, "query": q, "hits": len(pack.items)},
                )
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
            return IndexMapResponse(text=_live_indexer().repo_map(record.id.value))

    GITHUB_APP_CREATE_URL = "https://github.com/settings/apps/new"

    def _app_status_model(status: GithubAppStatus) -> GithubAppStatusModel:
        install_url = (
            f"https://github.com/apps/{status.slug}/installations/new" if status.slug else None
        )
        return GithubAppStatusModel(
            registered=status.registered,
            installed=status.installed,
            verified=status.verified,
            app_id=status.app_id,
            slug=status.slug,
            create_url=GITHUB_APP_CREATE_URL,
            install_url=install_url,
        )

    @app.get("/github/status", response_model=GithubStatusResponse)
    def github_status(_: None = Depends(require_auth)) -> GithubStatusResponse:
        with github_service() as service:
            status = service.status()
            enrolled = None
            with repository_service() as repos:
                enrolled = _enrolled_github(repos)
            return GithubStatusResponse(
                controller=_app_status_model(status.controller),
                reviewer=_app_status_model(status.reviewer),
                webhook_enabled=status.webhook_enabled,
                poll_mode=status.poll_mode,
                github_cli_present=status.github_cli_present,
                enrolled=enrolled,
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

    @app.post("/github/apps/{role}/convert", response_model=GithubAppRecordResponse)
    def github_convert_app(
        role: str, body: GithubManifestConvertRequest, _: None = Depends(require_auth)
    ) -> GithubAppRecordResponse:
        if role not in APP_ROLES:
            raise HTTPException(status_code=404, detail="not found")
        if body.gh_token:
            raise HTTPException(status_code=400, detail="GH_TOKEN is not accepted")
        with github_service() as service:
            try:
                record = service.convert_manifest(role=role, code=body.code)
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
            except ForgeTransientError as error:
                raise HTTPException(status_code=502, detail=str(error)) from error
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
            except ForgeTransientError as error:
                raise HTTPException(status_code=502, detail=str(error)) from error
            return {"id": applied.id, "strict": applied.strict, "created": applied.created}

    @app.get("/goals", response_model=GoalListResponse)
    def goals(_: None = Depends(require_auth)) -> GoalListResponse:
        with goal_service() as service:
            return GoalListResponse(goals=[_goal_model(item) for item in service.list()])

    @app.post("/goals", response_model=GoalModel)
    def create_goal(body: GoalCreateRequest, _: None = Depends(require_auth)) -> GoalModel:
        try:
            source = GoalSource(body.source)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="unknown goal source") from error
        try:
            spec = GoalSpec(
                repository_id=_parse_id(body.repository_id),
                title=body.title,
                success_criteria=body.success_criteria,
                non_goals=body.non_goals,
                risk_ceiling=body.risk_ceiling,
                source=source,
                schedule=body.schedule,
                max_attempts=body.max_attempts,
            )
        except (GoalValidationError, IdentifierError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        with goal_service() as service:
            try:
                created = service.create(spec)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error
            return _goal_model(created)

    @app.get("/goals/{goal_id}", response_model=GoalDetailResponse)
    def get_goal(goal_id: str, _: None = Depends(require_auth)) -> GoalDetailResponse:
        with goal_service() as service:
            try:
                goal = service.get(GoalId(goal_id))
            except (LookupError, IdentifierError) as error:
                raise HTTPException(status_code=404, detail="not found") from error
            tasks = service.list_tasks(goal.id)
            return GoalDetailResponse(
                goal=_goal_model(goal),
                tasks=[
                    TaskModel(
                        id=item.id.value,
                        goal_id=item.goal_id.value,
                        title=item.title,
                        state=item.state.value,
                        kind=item.kind.value,
                        stop_reason=item.stop_reason,
                        pr_url=item.pr_url,
                        pr_base=item.pr_base,
                    )
                    for item in tasks
                ],
            )

    @app.post("/goals/{goal_id}/plan", response_model=GoalDetailResponse)
    def plan_goal(goal_id: str, _: None = Depends(require_auth)) -> GoalDetailResponse:
        try:
            ident = GoalId(goal_id)
        except IdentifierError as error:
            raise HTTPException(status_code=404, detail="not found") from error
        with goal_engine() as engine:
            try:
                engine.plan(ident)
                goal = engine.get_goal(ident)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error
            except InvalidTransition as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            except (
                SchemaError,
                UnresolvedEvidence,
                WipExceeded,
                BudgetExceeded,
                BreakerTripped,
                GoalValidationError,
            ) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            tasks = engine.list_tasks(goal.id)
            return GoalDetailResponse(
                goal=_goal_model(goal),
                tasks=[
                    TaskModel(
                        id=item.id.value,
                        goal_id=item.goal_id.value,
                        title=item.title,
                        state=item.state.value,
                        kind=item.kind.value,
                        stop_reason=item.stop_reason,
                        pr_url=item.pr_url,
                        pr_base=item.pr_base,
                    )
                    for item in tasks
                ],
            )

    @app.post("/goals/tick", response_model=GoalTickResponse)
    def tick_goals(_: None = Depends(require_auth)) -> GoalTickResponse:
        with goal_engine() as engine:
            result = engine.tick()
            return GoalTickResponse(
                ok=result.ok,
                status=result.status,
                reason=result.reason,
                task_id=result.task_id,
                pr_url=result.pr_url,
                terminal=result.terminal,
            )

    @app.post("/goals/ingest", response_model=GoalModel)
    def ingest_goal(body: GoalIngestRequest, _: None = Depends(require_auth)) -> GoalModel:
        try:
            repo_id = _parse_id(body.repository_id)
            if body.source == "github_issue":
                with goal_engine() as engine:
                    created = engine.ingest_github_issue(
                        repository_id=repo_id,
                        title=body.title,
                        body=body.body or body.success_criteria,
                        non_goals=body.non_goals,
                        risk_ceiling=body.risk_ceiling,
                        max_attempts=body.max_attempts,
                    )
            elif body.source == "schedule":
                with goal_engine() as engine:
                    created = engine.ingest_schedule(
                        repository_id=repo_id,
                        title=body.title,
                        success_criteria=body.success_criteria or body.body,
                        non_goals=body.non_goals,
                        schedule=body.schedule or "",
                        max_attempts=body.max_attempts,
                        risk_ceiling=body.risk_ceiling,
                    )
            else:
                raise HTTPException(status_code=400, detail="unknown ingest source")
        except GoalValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except LookupError as error:
            raise HTTPException(status_code=404, detail="not found") from error
        return _goal_model(created)

    @app.get("/runs", response_model=RunListResponse)
    def list_runs(_: None = Depends(require_auth)) -> RunListResponse:
        with goal_service() as service:
            return RunListResponse(
                runs=[
                    RunModel(
                        id=item.id.value,
                        goal_id=item.goal_id.value,
                        task_id=item.task_id.value,
                        status=item.status,
                        evidence=item.evidence,
                        pr_url=item.pr_url,
                    )
                    for item in service.list_runs()
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

    @app.get("/skills")
    def list_skills(_: None = Depends(require_auth)) -> dict[str, object]:
        with skill_catalog() as catalog:
            return {"skills": [skill_to_dict(item) for item in catalog.list()]}

    @app.post("/skills/import")
    def import_skill(
        body: SkillImportRequest, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                skill = catalog.import_pack(
                    body.locator,
                    body.revision,
                    scope=body.scope,
                    repository_id=body.repository_id,
                )
            except (
                MutableRevisionError,
                NetworkFetchForbidden,
                SkillStillQuarantined,
                FileNotFoundError,
            ) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return skill_to_dict(skill)

    @app.get("/skills/{skill_id}")
    def get_skill(skill_id: str, _: None = Depends(require_auth)) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                return skill_to_dict(catalog.get(skill_id), include_body=True)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error

    @app.post("/skills/{skill_id}/evaluate")
    def evaluate_installed_skill(
        skill_id: str, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                skill = catalog.evaluate(skill_id)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error
            result = evaluate_skill(skill)
            payload = skill_to_dict(skill)
            payload["evaluation"] = {
                "passed": result.passed,
                "security_passed": result.security_passed,
                "regression_passed": result.regression_passed,
                "reasons": list(result.reasons),
            }
            return payload

    @app.post("/skills/{skill_id}/approve")
    def approve_skill(
        skill_id: str, body: SkillApproveRequest, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                skill = catalog.approve(skill_id, human=body.human)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error
            except (HumanApprovalRequired, SkillStillQuarantined) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return skill_to_dict(skill)

    @app.post("/skills/{skill_id}/activate")
    def activate_skill(skill_id: str, _: None = Depends(require_auth)) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                skill = catalog.activate(skill_id)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error
            except (SkillStillQuarantined, HumanApprovalRequired, PromotionBlocked) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return skill_to_dict(skill)

    @app.post("/skills/{skill_id}/disable")
    def disable_skill(skill_id: str, _: None = Depends(require_auth)) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                skill = catalog.disable(skill_id, "operator")
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error
            return skill_to_dict(skill)

    @app.post("/skills/{skill_id}/promote")
    def promote_skill(
        skill_id: str, body: SkillApproveRequest, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                record = activate_promoted(catalog, skill_id, human=body.human)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="not found") from error
            except (HumanApprovalRequired, PromotionBlocked, SkillStillQuarantined) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return _memory_dict(record)

    @app.post("/skills/route")
    def route_installed_skills(
        body: SkillRouteRequest, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with skill_catalog() as catalog:
            routed = catalog.route(
                body.query,
                budget_tokens=body.budget_tokens,
                selected_name=body.selected_name,
            )
            selected = None
            if routed.selected is not None:
                selected = {
                    "name": routed.selected.name,
                    "description": routed.selected.description,
                    "body": routed.selected.body,
                }
            return {
                "summaries": [
                    {
                        "name": item.name,
                        "description": item.description,
                        "body": item.body,
                    }
                    for item in routed.summaries
                ],
                "selected": selected,
                "omitted": list(routed.omitted),
                "tokens_used": routed.tokens_used,
            }

    @app.get("/memory")
    def list_memory(_: None = Depends(require_auth)) -> dict[str, object]:
        with skill_catalog() as catalog:
            return {"records": [_memory_dict(item) for item in catalog.procedural.list()]}

    @app.post("/memory/import-lessons")
    def import_lessons(
        body: LessonImportRequest, _: None = Depends(require_auth)
    ) -> dict[str, object]:
        with skill_catalog() as catalog:
            try:
                records = catalog.procedural.import_lessons(body.yaml)
            except MemoryRejected as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return {"records": [_memory_dict(item) for item in records]}

    @app.get("/memory/{record_id}")
    def get_memory(record_id: str, _: None = Depends(require_auth)) -> dict[str, object]:
        with skill_catalog() as catalog:
            record = catalog.procedural.get(record_id) or catalog.episodic.get(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail="not found")
            return _memory_dict(record)

    @app.get("/telegram/status", response_model=TelegramStatusResponse)
    def telegram_status(_: None = Depends(require_auth)) -> TelegramStatusResponse:
        conn = database.connect()
        try:
            settings_row = SqliteTelegramStore(conn).load()
            return TelegramStatusResponse(
                token_present=bool(store.get(BOT_TOKEN_REF)),
                allowed_user_ids=sorted(settings_row.allowed_user_ids),
                allowed_chat_ids=sorted(settings_row.allowed_chat_ids),
                default_repository_id=settings_row.default_repository_id,
                last_update_offset=settings_row.last_update_offset,
                botfather_url=BOTFATHER_URL,
                setup_steps=list(BOTFATHER_STEPS),
            )
        finally:
            conn.close()

    @app.post("/telegram/token")
    def telegram_store_token(
        body: TelegramTokenRequest, _: None = Depends(require_auth)
    ) -> dict[str, bool]:
        token = body.token.strip()
        if not token:
            raise HTTPException(status_code=400, detail="bot token is required")
        store.put(BOT_TOKEN_REF, token)
        return {"token_present": True}

    @app.put("/telegram/allowlist", response_model=TelegramStatusResponse)
    def telegram_allowlist(
        body: TelegramAllowlistRequest, _: None = Depends(require_auth)
    ) -> TelegramStatusResponse:
        conn = database.connect()
        try:
            telegram_store = SqliteTelegramStore(conn)
            default = body.default_repository_id or None
            if default is not None and default.strip() == "":
                default = None
            telegram_store.save_allowlist(
                tuple(body.allowed_user_ids),
                tuple(body.allowed_chat_ids),
                default_repository_id=default,
            )
        finally:
            conn.close()
        return telegram_status()

    @app.post("/telegram/poll")
    def telegram_poll(_: None = Depends(require_auth)) -> dict[str, int]:
        with telegram_connector() as connector:
            handled = connector.poll()
            return {"handled": handled}

    @app.get("/ops/dashboard")
    def ops_dashboard(
        _: None = Depends(require_auth),
        x_kronos_client_version: Annotated[str | None, Header(alias=CLIENT_VERSION_HEADER)] = None,
    ) -> dict[str, object]:
        with doctor_service() as doctor:
            snap = doctor.dashboard(
                client_version=x_kronos_client_version or settings.engine_version
            )
            return {
                "ready": snap.ready,
                "repositories": snap.repositories,
                "schedules": snap.schedules,
                "budgets": snap.budgets,
                "runs": snap.runs,
                "diffs": snap.diffs,
                "tests": snap.tests,
                "index": snap.index,
            }

    @app.get("/ops/doctor")
    def ops_doctor(
        _: None = Depends(require_auth),
        x_kronos_client_version: Annotated[str | None, Header(alias=CLIENT_VERSION_HEADER)] = None,
    ) -> dict[str, object]:
        with doctor_service() as doctor:
            report = doctor.check(client_version=x_kronos_client_version or settings.engine_version)
            return {
                "ready": report.ready,
                "health": report.health,
                "compatible": report.compatible,
                "model_degraded": report.model_degraded,
                "index_degraded": report.index_degraded,
                "findings": [item.detail for item in report.findings],
            }

    @app.post("/ops/backup")
    def ops_backup(body: BackupRequest, _: None = Depends(require_auth)) -> dict[str, object]:
        with doctor_service() as doctor:
            dest = (
                Path(body.dest) if body.dest.strip() else settings.paths.data / "backups" / "latest"
            )
            archive = doctor.backup(dest)
            return {"path": archive.path, "includes_secret_store": archive.includes_secret_store}

    @app.get("/ops/dead-letters")
    def ops_dead_letters(_: None = Depends(require_auth)) -> dict[str, object]:
        with doctor_service() as doctor:
            return {
                "items": [
                    {
                        "id": item.id,
                        "event_type": item.event_type,
                        "payload": item.payload,
                        "reason": item.reason,
                    }
                    for item in doctor.inspect_dead_letters()
                ]
            }

    @app.post("/ops/leases/recover")
    def ops_recover_leases(_: None = Depends(require_auth)) -> dict[str, object]:
        with doctor_service() as doctor:
            recovered = doctor.recover_stuck_leases(now=datetime.now(tz=UTC))
            return {"recovered": [item.resource_key for item in recovered]}

    @app.get("/ops/settings")
    def ops_get_settings(_: None = Depends(require_auth)) -> dict[str, bool]:
        with doctor_service() as doctor:
            current = doctor.settings()
            return {"otel_export": current.otel_export, "langfuse_export": current.langfuse_export}

    @app.put("/ops/settings")
    def ops_put_settings(
        body: OpsSettingsRequest,
        request: Request,
        _: None = Depends(require_auth),
    ) -> dict[str, bool]:
        with doctor_service() as doctor:
            saved = doctor.save_settings(
                OpsSettings(otel_export=body.otel_export, langfuse_export=body.langfuse_export)
            )
        active = getattr(request.app.state, "tracer", None)
        if isinstance(active, Tracer):
            active.set_export_flags(
                otel_export=saved.otel_export, langfuse_export=saved.langfuse_export
            )
        return {"otel_export": saved.otel_export, "langfuse_export": saved.langfuse_export}

    @app.get("/ops/updates")
    def ops_updates(
        _: None = Depends(require_auth),
        x_kronos_client_version: Annotated[str | None, Header(alias=CLIENT_VERSION_HEADER)] = None,
    ) -> dict[str, object]:
        with doctor_service() as doctor:
            return doctor.updates(client_version=x_kronos_client_version or "")

    @app.get("/ops/notifications")
    def ops_notifications(_: None = Depends(require_auth)) -> dict[str, object]:
        with doctor_service() as doctor:
            return {
                "items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "detail": item.detail,
                        "severity": item.severity,
                    }
                    for item in doctor.notifications()
                ]
            }

    @app.post("/ops/rollback")
    def ops_rollback(_: None = Depends(require_auth)) -> dict[str, str]:
        from kronos_engine.ops.lifecycle import install as install_release
        from kronos_engine.ops.lifecycle import rollback as rollback_release

        target = settings.paths.data / "release"
        if not (target / "current" / "version.json").is_file():
            install_release(
                target, version=settings.engine_version, engine_version=settings.engine_version
            )
        state = rollback_release(target)
        return {"version": state.version}

    return app


def _github_record(record: GithubAppRecord) -> GithubAppRecordResponse:
    return GithubAppRecordResponse(
        role=record.role,
        registered=True,
        installed=record.installation_id is not None,
        verified=record.verified,
        app_id=record.app_id,
        slug=record.slug,
    )


def _enrolled_github(repos: RepositoryService) -> GithubEnrolledModel | None:
    for record in repos.list():
        parsed = github_owner_repo(record.origin)
        if parsed is None:
            continue
        owner, name = parsed
        return GithubEnrolledModel(
            owner=owner,
            repo=name,
            integration_branch=record.policy.branches.integration,
            protected_branch=record.policy.branches.protected,
        )
    return None


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


def _embedding_backend_model(resolved: ResolvedEmbedder) -> EmbeddingBackendModel:
    kind = resolved.backend.kind
    if kind not in {"openai_compatible", "onnx", "none"}:
        kind = "none"
    return EmbeddingBackendModel(
        kind=kind,  # type: ignore[arg-type]
        model_id=resolved.backend.model_id,
        display_name=resolved.backend.display_name,
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
        state=status.state,
        files_done=status.files_done,
        files_total=status.files_total,
        chunks_embedded=status.chunks_embedded,
        chunks_skipped=status.chunks_skipped,
        last_activity_at=status.last_activity_at,
        watch_enabled=status.watch_enabled,
    )


def _goal_model(goal: GoalRecord) -> GoalModel:
    return GoalModel(
        id=goal.id.value,
        repository_id=goal.repository_id.value,
        title=goal.title,
        state=goal.state.value,
        source=goal.source.value,
        risk_ceiling=goal.risk_ceiling,
        success_criteria=goal.success_criteria,
        non_goals=goal.non_goals,
        stop_reason=goal.stop_reason,
        schedule=goal.schedule,
        max_attempts=goal.max_attempts,
    )


def _memory_dict(record: MemoryRecord) -> dict[str, object]:
    status = record.status.value if hasattr(record.status, "value") else record.status
    return {
        "id": record.id,
        "kind": record.kind,
        "text": record.text,
        "source_sha": record.source_sha,
        "outcome": record.outcome,
        "confidence": record.confidence,
        "helpful": record.helpful,
        "harmful": record.harmful,
        "status": status,
        "skill_id": record.skill_id,
        "independent_sources": list(record.independent_sources),
    }
