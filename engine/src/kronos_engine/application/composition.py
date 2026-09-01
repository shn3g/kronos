# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compose planning, dispatch, verification, and merge onto one connection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from kronos_engine.adapters.executors.controlled import ControlledOpenExecutor
from kronos_engine.adapters.executors.cursor import CursorExecutor, detect_cursor_cli
from kronos_engine.adapters.executors.opencode import OpencodeExecutor, detect_opencode_cli
from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.application.dispatch import DispatchService
from kronos_engine.application.embeddings import resolve_embedder
from kronos_engine.application.gates import ProcessGateRunner
from kronos_engine.application.github_setup import GitHubSetupService
from kronos_engine.application.goal_engine import GoalEngine
from kronos_engine.application.goals import GoalService
from kronos_engine.application.merge import MergeService
from kronos_engine.application.notifications import NotificationService
from kronos_engine.application.planning import IndexedPlanner, LlmPlanner, Planner, PlanningService
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.recovery import RecoveryService
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.application.unavailable_forge import UnavailableForge
from kronos_engine.application.verification import GateRunner, VerificationService
from kronos_engine.config.repository import github_owner_repo
from kronos_engine.config.settings import Settings
from kronos_engine.domain.attestations import ATTESTATION_HMAC_KEY_REF, ATTESTATION_VERIFY_KEY_REF
from kronos_engine.indexing.service import IndexingService
from kronos_engine.ports.executor import Executor
from kronos_engine.ports.forge import ForgeAuthError, ForgeTarget
from kronos_engine.ports.secrets import SecretStore
from kronos_engine.skills.catalog import SkillCatalog, bundled_skills_root
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.github_apps import SqliteGithubAppStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.leases import SqliteLeases
from kronos_engine.state.model_profiles import SqliteModelRegistry
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry
from kronos_engine.state.scheduler import GoalScheduler


def build_goal_engine(
    conn: object,
    settings: Settings,
    secrets: SecretStore,
    github_http: object,
    *,
    planner: Planner | None = None,
    executor: Executor | None = None,
    gates: GateRunner | None = None,
    forge: object | None = None,
    clock: Callable[[], datetime] | None = None,
    notifications: NotificationService | None = None,
) -> GoalEngine:
    tick = clock or (lambda: datetime.now(tz=UTC))
    store = SqliteGoalStore(conn)  # type: ignore[arg-type]
    events = SqliteEventStore(conn)  # type: ignore[arg-type]
    outbox = SqliteOutbox(conn)  # type: ignore[arg-type]
    recorder = Recorder(conn, events, outbox)  # type: ignore[arg-type]
    leases = SqliteLeases(conn)  # type: ignore[arg-type]
    registry = SqliteModelRegistry(conn)  # type: ignore[arg-type]
    embeddings = resolve_embedder(
        registry,
        secrets,
        settings.paths.cache / "models",
    ).adapter
    indexer = IndexingService(settings.paths, embeddings=embeddings)
    repos = RepositoryService(
        SqliteRepositoryRegistry(conn),  # type: ignore[arg-type]
        settings.paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
        indexer=indexer,
    )
    goals = GoalService(store, repos, recorder, notifications=notifications)
    indexed = IndexedPlanner(indexer)
    chosen_planner = planner or LlmPlanner(registry, secrets, indexed)
    chosen_executor = executor or _executor_from_repos(repos)
    chosen_gates = gates or ProcessGateRunner()
    chosen_forge = forge if forge is not None else _controller_forge(
        conn, settings, secrets, github_http, repos
    )
    merge = MergeService(
        chosen_forge,  # type: ignore[arg-type]
        attestation_key=_attestation_key(secrets),
        expected_reviewer_app_id=_app_id(conn, "reviewer"),
        expected_controller_app_id=_app_id(conn, "controller"),
    )
    planning = PlanningService(store, repos, recorder, chosen_planner, clock=tick)
    skills = SkillCatalog(
        conn,  # type: ignore[arg-type]
        skills_root=bundled_skills_root(),
        store_dir=settings.paths.cache / "skills",
        embeddings=embeddings,
    )
    skills.load_core()
    dispatch = DispatchService(
        store,
        repos,
        leases,
        recorder,
        indexer,
        chosen_executor,
        lambda worktree: ProcessJailSandbox(worktree),
        settings.paths.cache,
        clock=tick,
        skills=skills,
        notifications=notifications,
    )
    verification = VerificationService(
        store,
        repos,
        recorder,
        chosen_forge,
        chosen_gates,
        leases,
        clock=tick,
    )
    recovery = RecoveryService(store, recorder)
    scheduler = GoalScheduler(store, goals, leases, clock=tick)
    return GoalEngine(
        store, planning, dispatch, verification, recovery, merge, scheduler, clock=tick,
        notifications=notifications,
    )


def select_executor(profile: str) -> Executor:
    name = "controlled" if profile in {"standard", "controlled", ""} else profile
    if name == "cursor" and detect_cursor_cli() is not None:
        return CursorExecutor()
    if name == "opencode" and detect_opencode_cli() is not None:
        return OpencodeExecutor()
    return ControlledOpenExecutor()


def _executor_from_repos(repos: RepositoryService) -> Executor:
    chosen = "controlled"
    for record in repos.list():
        name = record.policy.executor.profile
        if name in {"cursor", "opencode"}:
            chosen = name
            break
    return select_executor(chosen)


def _attestation_key(secrets: SecretStore) -> bytes:
    raw = secrets.get(ATTESTATION_VERIFY_KEY_REF) or secrets.get(ATTESTATION_HMAC_KEY_REF) or ""
    return raw.encode()


def _app_id(conn: object, role: str) -> int:
    record = SqliteGithubAppStore(conn).get(role)  # type: ignore[arg-type]
    if record is None:
        return 0
    return int(record.app_id)


def _controller_forge(
    conn: object,
    settings: Settings,
    secrets: SecretStore,
    github_http: object,
    repos: RepositoryService,
) -> object:
    _ = settings
    enrolled = None
    for record in repos.list():
        parsed = github_owner_repo(record.origin)
        if parsed is not None:
            enrolled = (record, parsed)
            break
    if enrolled is None:
        return UnavailableForge()
    record, (owner, name) = enrolled
    try:
        setup = GitHubSetupService(SqliteGithubAppStore(conn), secrets, github_http)  # type: ignore[arg-type]
        return setup.forge(
            "controller",
            ForgeTarget(
                owner=owner,
                repo=name,
                integration_branch=record.policy.branches.integration,
                protected_branch=record.policy.branches.protected,
            ),
        )
    except ForgeAuthError:
        return UnavailableForge()
