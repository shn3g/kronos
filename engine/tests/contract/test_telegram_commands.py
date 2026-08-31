# SPDX-License-Identifier: AGPL-3.0-or-later
"""Telegram commands call GoalService. Fixture transport is the contract."""

from __future__ import annotations

from pathlib import Path

from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore
from tests.support.telegram_fixture import ALLOWED_CHAT, ALLOWED_USER, BOT_TOKEN, TelegramFixture

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.application.goals import GoalService
from kronos_engine.application.notifications import NotificationService
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.paths import resolve_paths
from kronos_engine.domain.entities import RepositoryId
from kronos_engine.domain.goals import GoalSource, GoalSpec, GoalState
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry
from kronos_engine.state.telegram import SqliteTelegramStore
from kronos_engine.telegram.artifacts import supported_artifact
from kronos_engine.telegram.client import TelegramBotClient
from kronos_engine.telegram.commands import TelegramConnector
from kronos_engine.telegram.formatting import format_state_change, redact_secrets


def _paths(tmp_path: Path):
    return resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )


def _stack(tmp_path: Path, *, default_repo: str | None = None):
    paths = _paths(tmp_path)
    database = Database(paths.database)
    conn = database.connect()
    secrets = InMemorySecretStore()
    secrets.put("telegram:bot_token", BOT_TOKEN)
    fixture = TelegramFixture()
    repos = RepositoryService(
        SqliteRepositoryRegistry(conn),
        paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
    )
    store = SqliteTelegramStore(conn)
    store.save_allowlist((ALLOWED_USER,), (ALLOWED_CHAT,), default_repository_id=default_repo)
    client = TelegramBotClient(secrets, fixture)
    notifier = NotificationService(client, store)
    goals = GoalService(
        SqliteGoalStore(conn),
        repos,
        Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)),
        notifications=notifier,
    )
    connector = TelegramConnector(
        client=client,
        store=store,
        secrets=secrets,
        goals=goals,
        repos=repos,
        notifications=notifier,
    )
    return connector, fixture, goals, repos, store, conn


def _enrol_named(tmp_path: Path, repos: RepositoryService, name: str) -> str:
    root = init_git_repo(
        tmp_path / name,
        origin=f"https://github.com/acme/{name}.git",
        files={"README.md": f"{name}\n"},
    )
    return repos.enrol(str(root)).id.value


def test_help_lists_supported_commands(tmp_path: Path) -> None:
    connector, fixture, _goals, repos, _store, conn = _stack(tmp_path)
    _enrol_named(tmp_path, repos, "alpha")
    fixture.queue_message(update_id=1, text="/help")
    connector.poll()
    body = "\n".join(fixture.texts_to(ALLOWED_CHAT)).lower()
    for name in ("goal", "status", "pause", "resume", "approval", "help"):
        assert name in body
    conn.close()


def test_goal_command_uses_goal_service_same_as_desktop(tmp_path: Path) -> None:
    connector, fixture, goals, repos, _store, conn = _stack(tmp_path)
    repo_id = _enrol_named(tmp_path, repos, "alpha")
    desktop = goals.create(
        GoalSpec(
            repository_id=RepositoryId(repo_id),
            title="Fix add",
            success_criteria="add returns a+b",
            non_goals="rewrite packaging",
            risk_ceiling="low",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )
    fixture.queue_message(
        update_id=2,
        text=f"/goal repo:{repo_id} | Fix add | add returns a+b | rewrite packaging | low",
    )
    connector.poll()
    listed = list(goals.list())
    assert len(listed) == 2
    telegram = next(item for item in listed if item.id != desktop.id)
    assert telegram.state is desktop.state is GoalState.DRAFT
    assert telegram.repository_id == desktop.repository_id
    assert telegram.title == desktop.title
    assert telegram.success_criteria == desktop.success_criteria
    assert telegram.source is GoalSource.TELEGRAM
    assert desktop.source is GoalSource.DESKTOP
    conn.close()


def test_pause_resume_and_approval_are_goal_service_transitions(tmp_path: Path) -> None:
    connector, fixture, goals, repos, _store, conn = _stack(tmp_path)
    repo_id = _enrol_named(tmp_path, repos, "alpha")
    desktop = goals.create(
        GoalSpec(
            repository_id=RepositoryId(repo_id),
            title="Desktop",
            success_criteria="done",
            non_goals="scope",
            risk_ceiling="low",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )
    fixture.queue_message(
        update_id=3,
        text=f"/goal repo:{repo_id} | Telegram | done | scope | low",
    )
    connector.poll()
    telegram = next(item for item in goals.list() if item.id != desktop.id)
    goals.transition(desktop.id, GoalState.PLANNED)
    goals.transition(telegram.id, GoalState.PLANNED)
    fixture.queue_message(update_id=4, text=f"/pause {telegram.id.value}")
    connector.poll()
    goals.transition(desktop.id, GoalState.PAUSED, reason="operator")
    assert goals.get(telegram.id).state is GoalState.PAUSED
    assert goals.get(desktop.id).state is GoalState.PAUSED
    fixture.queue_message(update_id=5, text=f"/resume {telegram.id.value}")
    connector.poll()
    goals.transition(desktop.id, GoalState.ACTIVE)
    assert goals.get(telegram.id).state is GoalState.ACTIVE
    assert goals.get(desktop.id).state is GoalState.ACTIVE
    goals.transition(telegram.id, GoalState.PAUSED, reason="human-gate")
    fixture.queue_message(update_id=6, text=f"/approval {telegram.id.value}")
    connector.poll()
    assert goals.get(telegram.id).state is GoalState.ACTIVE
    conn.close()


def test_ambiguous_repository_command_fails_without_creating_a_goal(tmp_path: Path) -> None:
    connector, fixture, goals, repos, store, conn = _stack(tmp_path, default_repo=None)
    _enrol_named(tmp_path, repos, "alpha")
    _enrol_named(tmp_path, repos, "beta")
    store.save_allowlist((ALLOWED_USER,), (ALLOWED_CHAT,), default_repository_id=None)
    fixture.queue_message(
        update_id=7,
        text="/goal | Ambiguous | criteria | non-goals | low",
    )
    connector.poll()
    assert goals.list() == ()
    body = "\n".join(fixture.texts_to(ALLOWED_CHAT)).lower()
    assert "repository" in body
    conn.close()


def test_safe_configured_default_repository_is_used_when_explicit_id_omitted(
    tmp_path: Path,
) -> None:
    connector, fixture, goals, repos, store, conn = _stack(tmp_path)
    alpha = _enrol_named(tmp_path, repos, "alpha")
    _enrol_named(tmp_path, repos, "beta")
    store.save_allowlist((ALLOWED_USER,), (ALLOWED_CHAT,), default_repository_id=alpha)
    fixture.queue_message(
        update_id=8,
        text="/goal | Defaulted | criteria | non-goals | low",
    )
    connector.poll()
    listed = list(goals.list())
    assert len(listed) == 1
    assert listed[0].repository_id.value == alpha
    conn.close()


def test_goal_at_bot_name_creates_a_goal(tmp_path: Path) -> None:
    connector, fixture, goals, repos, _store, conn = _stack(tmp_path)
    repo_id = _enrol_named(tmp_path, repos, "alpha")
    fixture.queue_message(
        update_id=80,
        text=f"/goal@KronosBot repo:{repo_id} Ship it | done | scope | low",
    )
    connector.poll()
    listed = list(goals.list())
    assert len(listed) == 1
    assert listed[0].title == "Ship it"
    assert listed[0].success_criteria == "done"
    assert listed[0].source is GoalSource.TELEGRAM
    conn.close()


def test_unknown_explicit_repository_fails_safely(tmp_path: Path) -> None:
    connector, fixture, goals, repos, _store, conn = _stack(tmp_path)
    _enrol_named(tmp_path, repos, "alpha")
    fixture.queue_message(
        update_id=9,
        text="/goal repo:repo_missing | Title | criteria | non-goals | low",
    )
    connector.poll()
    assert goals.list() == ()
    conn.close()


def test_status_includes_state_pr_link_and_failure_without_logs(tmp_path: Path) -> None:
    connector, fixture, goals, repos, _store, conn = _stack(tmp_path)
    repo_id = _enrol_named(tmp_path, repos, "alpha")
    goal = goals.create(
        GoalSpec(
            repository_id=RepositoryId(repo_id),
            title="Ship PR",
            success_criteria="merged",
            non_goals="docs",
            risk_ceiling="low",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )
    goals.transition(goal.id, GoalState.PLANNED)
    goals.transition(goal.id, GoalState.PAUSED, reason="breaker open")
    fixture.queue_message(update_id=10, text="/status")
    connector.poll()
    body = "\n".join(fixture.texts_to(ALLOWED_CHAT))
    assert "Ship PR" in body
    assert "paused" in body.lower()
    assert "breaker" in body.lower()
    connector.notifications.notify_state_change(
        chat_id=ALLOWED_CHAT,
        title=goal.title,
        state="active",
        pr_url="https://github.com/acme/alpha/pull/12",
        extra="budget remaining 2",
    )
    connector.notifications.notify_artifact(
        chat_id=ALLOWED_CHAT,
        name="test-report.txt",
        content="1 failed, 2 passed",
    )
    later = "\n".join(fixture.texts_to(ALLOWED_CHAT))
    assert "https://github.com/acme/alpha/pull/12" in later
    assert "test-report.txt" in later
    assert "1 failed, 2 passed" in later
    conn.close()


def test_fixture_transport_is_not_live_bot_api(tmp_path: Path) -> None:
    _connector, fixture, _goals, _repos, _store, conn = _stack(tmp_path)
    assert fixture.base_url == "fixture://telegram"
    assert "api.telegram.org" not in fixture.base_url
    conn.close()


def test_formatting_redacts_secret_shaped_values_and_keeps_pr_links() -> None:
    raw = (
        "goal failed ghp_abcdefghijklmnopqrstuvwxyz0123456789 "
        "https://github.com/acme/alpha/pull/4 bearer=AAAA.BBBB"
    )
    cleaned = redact_secrets(raw)
    assert "ghp_" not in cleaned
    assert "https://github.com/acme/alpha/pull/4" in cleaned
    assert "[redacted]" in cleaned
    message = format_state_change(
        title="Fix add",
        state="paused",
        pr_url="https://github.com/acme/alpha/pull/4",
        extra="breaker open",
    )
    assert "Fix add" in message
    assert "paused" in message
    assert "pull/4" in message
    assert "breaker" in message


def test_desktop_goal_service_notifies_allowed_chats_without_manual_notify(
    tmp_path: Path,
) -> None:
    _connector, fixture, goals, repos, _store, conn = _stack(tmp_path)
    repo_id = _enrol_named(tmp_path, repos, "alpha")
    fixture.sent.clear()
    created = goals.create(
        GoalSpec(
            repository_id=RepositoryId(repo_id),
            title="Desktop ship",
            success_criteria="merged",
            non_goals="docs",
            risk_ceiling="low",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )
    created_body = "\n".join(fixture.texts_to(ALLOWED_CHAT))
    assert fixture.sent
    assert "Desktop ship" in created_body
    assert "draft" in created_body.lower()
    fixture.sent.clear()
    goals.transition(created.id, GoalState.PLANNED)
    planned_body = "\n".join(fixture.texts_to(ALLOWED_CHAT))
    assert "planned" in planned_body.lower()
    fixture.sent.clear()
    goals.transition(
        created.id,
        GoalState.PAUSED,
        reason=f"forge failed {BOT_TOKEN} ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    )
    paused_body = "\n".join(fixture.texts_to(ALLOWED_CHAT))
    assert "paused" in paused_body.lower()
    assert BOT_TOKEN not in paused_body
    assert "ghp_" not in paused_body
    assert "[redacted]" in paused_body
    conn.close()


def test_unsupported_artifacts_are_refused() -> None:
    assert supported_artifact("test-report.txt", "ok") is True
    assert supported_artifact("summary.md", "# report") is True
    assert supported_artifact("id_rsa", "-----BEGIN OPENSSH PRIVATE KEY-----") is False
    assert supported_artifact("engine.log", "KRONOS_AUTH_TOKEN=secret") is False
    assert supported_artifact("key.pem", "-----BEGIN RSA PRIVATE KEY-----") is False
