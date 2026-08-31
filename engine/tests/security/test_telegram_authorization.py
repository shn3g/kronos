# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unauthorized users, replayed updates, and secret leak refusal fail closed."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore
from tests.support.telegram_fixture import (
    ALLOWED_CHAT,
    ALLOWED_USER,
    BOT_TOKEN,
    STRANGER_CHAT,
    STRANGER_USER,
    TelegramFixture,
)

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.api.app import create_app
from kronos_engine.application.goals import GoalService
from kronos_engine.application.notifications import NotificationService
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.domain.entities import RepositoryId
from kronos_engine.domain.goals import GoalSource, GoalSpec, GoalState
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry
from kronos_engine.state.telegram import SqliteTelegramStore
from kronos_engine.telegram.client import TelegramBotClient
from kronos_engine.telegram.commands import TelegramConnector


def _paths(tmp_path: Path):
    return resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )


def _enrol(tmp_path: Path, conn, name: str = "alpha") -> str:
    paths = _paths(tmp_path)
    repos = RepositoryService(
        SqliteRepositoryRegistry(conn),
        paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
    )
    root = init_git_repo(
        tmp_path / name,
        origin=f"https://github.com/acme/{name}.git",
        files={"README.md": f"{name}\n"},
    )
    return repos.enrol(str(root)).id.value


def _connector(
    tmp_path: Path,
    *,
    allow_users: tuple[int, ...] = (ALLOWED_USER,),
    allow_chats: tuple[int, ...] = (ALLOWED_CHAT,),
    token: str | None = BOT_TOKEN,
    default_repo: str | None = None,
    clock: object | None = None,
):
    paths = _paths(tmp_path)
    database = Database(paths.database)
    conn = database.connect()
    secrets = InMemorySecretStore()
    if token is not None:
        secrets.put("telegram:bot_token", token)
    fixture = TelegramFixture()
    repos = RepositoryService(
        SqliteRepositoryRegistry(conn),
        paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
    )
    goals = GoalService(
        SqliteGoalStore(conn),
        repos,
        Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)),
    )
    store = SqliteTelegramStore(conn)
    store.save_allowlist(allow_users, allow_chats, default_repository_id=default_repo)
    client = TelegramBotClient(secrets, fixture)
    notifier = NotificationService(client, store)
    connector = TelegramConnector(
        client=client,
        store=store,
        secrets=secrets,
        goals=goals,
        repos=repos,
        notifications=notifier,
        clock=clock,
    )
    return connector, fixture, goals, repos, secrets, conn, database


def test_unauthorized_user_or_chat_is_dropped_without_goal_side_effects(tmp_path: Path) -> None:
    connector, fixture, goals, _repos, _secrets, conn, _db = _connector(tmp_path)
    repo_id = _enrol(tmp_path, conn)
    SqliteTelegramStore(conn).save_allowlist(
        (ALLOWED_USER,), (ALLOWED_CHAT,), default_repository_id=repo_id
    )
    command = (
        f"/goal repo:{repo_id} | Secret goal | criteria met | out of scope | low"
    )
    fixture.queue_message(update_id=1, user_id=STRANGER_USER, chat_id=ALLOWED_CHAT, text=command)
    fixture.queue_message(update_id=2, user_id=ALLOWED_USER, chat_id=STRANGER_CHAT, text=command)
    fixture.queue_message(
        update_id=3, user_id=STRANGER_USER, chat_id=STRANGER_CHAT, text=command
    )
    connector.poll()
    assert goals.list() == ()
    assert fixture.sent == []
    conn.close()


def test_empty_allowlist_fails_closed_even_with_a_bot_token(tmp_path: Path) -> None:
    connector, fixture, goals, _repos, _secrets, conn, _db = _connector(
        tmp_path, allow_users=(), allow_chats=()
    )
    repo_id = _enrol(tmp_path, conn)
    fixture.queue_message(
        update_id=1,
        text=f"/goal repo:{repo_id} | Title | criteria | non-goals | low",
    )
    connector.poll()
    assert goals.list() == ()
    assert fixture.sent == []
    conn.close()


def test_missing_bot_token_does_not_call_transport(tmp_path: Path) -> None:
    connector, fixture, goals, _repos, secrets, conn, _db = _connector(tmp_path, token=None)
    assert secrets.get("telegram:bot_token") is None
    fixture.queue_message(update_id=1, text="/help")
    connector.poll()
    assert fixture.get_calls == 0
    assert fixture.sent == []
    assert goals.list() == ()
    conn.close()


def test_replayed_update_id_is_ignored_after_restart(tmp_path: Path) -> None:
    connector, fixture, goals, _repos, secrets, conn, database = _connector(tmp_path)
    repo_id = _enrol(tmp_path, conn)
    SqliteTelegramStore(conn).save_allowlist(
        (ALLOWED_USER,), (ALLOWED_CHAT,), default_repository_id=repo_id
    )
    fixture.queue_message(
        update_id=41,
        text=f"/goal repo:{repo_id} | First | criteria | non-goals | low",
    )
    connector.poll()
    assert len(goals.list()) == 1
    first_id = goals.list()[0].id.value
    offset_after = SqliteTelegramStore(conn).load().last_update_offset
    assert offset_after == 42
    conn.close()

    conn = database.connect()
    paths = _paths(tmp_path)
    repos = RepositoryService(
        SqliteRepositoryRegistry(conn),
        paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
    )
    goals = GoalService(
        SqliteGoalStore(conn),
        repos,
        Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn)),
    )
    store = SqliteTelegramStore(conn)
    fixture.queue_message(
        update_id=41,
        text=f"/goal repo:{repo_id} | Replay | criteria | non-goals | low",
    )
    restarted = TelegramConnector(
        client=TelegramBotClient(secrets, fixture),
        store=store,
        secrets=secrets,
        goals=goals,
        repos=repos,
        notifications=NotificationService(TelegramBotClient(secrets, fixture), store),
    )
    restarted.poll()
    listed = goals.list()
    assert len(listed) == 1
    assert listed[0].id.value == first_id
    assert listed[0].title == "First"
    conn.close()


def test_bot_token_stays_in_secret_store_never_sqlite_or_messages(tmp_path: Path) -> None:
    connector, fixture, goals, _repos, secrets, conn, database = _connector(tmp_path)
    repo_id = _enrol(tmp_path, conn)
    SqliteTelegramStore(conn).save_allowlist(
        (ALLOWED_USER,), (ALLOWED_CHAT,), default_repository_id=repo_id
    )
    fixture.queue_message(
        update_id=5,
        text=(
            f"/goal repo:{repo_id} | leak {BOT_TOKEN} ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            " | criteria | non-goals | low"
        ),
    )
    connector.poll()
    assert secrets.get("telegram:bot_token") == BOT_TOKEN
    db_bytes = database._path.read_bytes()
    assert BOT_TOKEN.encode() not in db_bytes
    assert b"BEGIN RSA PRIVATE KEY" not in db_bytes
    combined = "\n".join(text for _chat, text in fixture.sent)
    assert BOT_TOKEN not in combined
    assert "ghp_" not in combined
    assert "[redacted]" in combined
    conn.close()


def test_notifications_redact_pem_bearer_and_reviewer_secrets(tmp_path: Path) -> None:
    connector, fixture, _goals, _repos, _secrets, conn, _db = _connector(tmp_path)
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAfakeprivatekeymaterialforredactiontestxx\n"
        "-----END RSA PRIVATE KEY-----"
    )
    connector.notifications.notify_failure(
        chat_id=ALLOWED_CHAT,
        reason=f"forge failed bearer install-token {pem} github:reviewer:private_key",
        log_excerpt="KRONOS_AUTH_TOKEN=install-token TRACE dump",
    )
    texts = fixture.texts_to(ALLOWED_CHAT)
    assert texts
    body = texts[-1]
    assert "BEGIN RSA" not in body
    assert "install-token" not in body
    assert "KRONOS_AUTH_TOKEN" not in body
    assert "private_key" not in body.lower() or "[redacted]" in body
    assert "TRACE dump" not in body
    conn.close()


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_rate_limit_blocks_command_and_approval_floods(tmp_path: Path) -> None:
    clock = _Clock(1_000.0)
    connector, fixture, goals, _repos, _secrets, conn, _db = _connector(tmp_path, clock=clock)
    repo_id = _enrol(tmp_path, conn)
    SqliteTelegramStore(conn).save_allowlist(
        (ALLOWED_USER,), (ALLOWED_CHAT,), default_repository_id=repo_id
    )
    for index in range(12):
        fixture.queue_message(update_id=100 + index, text="/help")
    connector.poll()
    help_replies = [text for text in fixture.texts_to(ALLOWED_CHAT) if "pause" in text.lower()]
    rate_replies = [text for text in fixture.texts_to(ALLOWED_CHAT) if "rate" in text.lower()]
    assert len(help_replies) == 10
    assert rate_replies
    goal = goals.create(
        GoalSpec(
            repository_id=RepositoryId(repo_id),
            title="Approve me",
            success_criteria="done",
            non_goals="scope",
            risk_ceiling="low",
            source=GoalSource.DESKTOP,
            max_attempts=3,
        )
    )
    goals.transition(goal.id, GoalState.PLANNED)
    goals.transition(goal.id, GoalState.PAUSED, reason="human-gate")
    fixture.sent.clear()
    for index in range(5):
        fixture.queue_message(update_id=200 + index, text=f"/approval {goal.id.value}")
    connector.poll()
    assert sum(1 for _c, text in fixture.sent if "rate" in text.lower()) >= 1
    conn.close()


@pytest.mark.asyncio
async def test_http_status_hides_token_and_rejects_webview_token_post(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    database = Database(paths.database)
    secrets = InMemorySecretStore()
    fixture = TelegramFixture()
    settings = Settings(
        engine_version="0.1.0",
        min_client_version="0.1.0",
        bind_host="127.0.0.1",
        bind_port=0,
        auth_token="install-token",
        paths=paths,
    )
    app = create_app(settings, database, secret_store=secrets, telegram_transport=fixture)
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        unauth = await http.get("/telegram/status")
        assert unauth.status_code == 401
        stored = await http.post("/telegram/token", headers=headers, json={"token": BOT_TOKEN})
        assert stored.status_code == 200
        assert BOT_TOKEN not in stored.text
        assert stored.json()["token_present"] is True
        assert secrets.get("telegram:bot_token") == BOT_TOKEN
        status = await http.get("/telegram/status", headers=headers)
        assert status.status_code == 200
        body = status.json()
        assert body["token_present"] is True
        assert "BotFather" in body["botfather_url"] or "t.me/BotFather" in body["botfather_url"]
        assert BOT_TOKEN not in str(body)
        assert "install-token" not in str(body)
        db_bytes = paths.database.read_bytes()
        assert BOT_TOKEN.encode() not in db_bytes
    finally:
        await http.aclose()
