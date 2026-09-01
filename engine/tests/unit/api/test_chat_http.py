# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.secrets import InMemorySecretStore

from kronos_engine.api.app import create_app
from kronos_engine.application.chat import ChatTurn
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.state.database import Database


class ScriptedCompleter:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)

    def complete(
        self,
        turns: Sequence[ChatTurn],
        system: str,
        *,
        cancel: object = None,
        on_delta: object = None,
    ) -> str:
        _ = turns, system, cancel, on_delta
        return self.replies.pop(0)


def _settings(tmp_path: Path) -> Settings:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    return Settings(
        engine_version="0.1.0",
        min_client_version="0.1.0",
        bind_host="127.0.0.1",
        bind_port=0,
        auth_token="install-token",
        paths=paths,
    )


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(
        _settings(tmp_path),
        database,
        secret_store=InMemorySecretStore(),
        chat_completer=ScriptedCompleter(["Staff is missing before the calendar route."]),
    )
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    try:
        yield http, {"Authorization": "Bearer install-token"}
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_chat_endpoints_fail_closed_and_round_trip(
    client: tuple[AsyncClient, dict[str, str]],
) -> None:
    http, headers = client
    unauth = await http.get("/chat/sessions")
    assert unauth.status_code == 401

    created = await http.post("/chat/sessions", headers=headers, json={})
    assert created.status_code == 200
    session_id = created.json()["session"]["id"]

    sent = await http.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "What is broken in onboarding?"},
    )
    assert sent.status_code == 200
    body = sent.json()
    roles = [item["role"] for item in body["messages"]]
    assert roles == ["user", "assistant"]
    assert "calendar" in body["messages"][1]["content"]

    missing = await http.get("/chat/sessions/chat_missing", headers=headers)
    assert missing.status_code == 404

    cancelled = await http.post(f"/chat/sessions/{session_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["ok"] is True


@pytest.mark.asyncio
async def test_revert_write_restores_file_and_fails_closed(
    tmp_path: Path,
) -> None:
    from tests.support.git_fixtures import init_git_repo
    from tests.support.secrets import InMemorySecretStore

    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(
        _settings(tmp_path),
        database,
        secret_store=InMemorySecretStore(),
        chat_completer=ScriptedCompleter(
            [
                '```tool\n{"name": "write_file", "path": "hello.py", "content": "new\\n"}\n```',
                "Updated hello.py.",
            ]
        ),
    )
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
        assert enrolled.status_code == 200
        repo_id = enrolled.json()["repository"]["id"]
        created = await http.post(
            "/chat/sessions", headers=headers, json={"repository_id": repo_id}
        )
        session_id = created.json()["session"]["id"]
        sent = await http.post(
            f"/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"content": "Patch hello.py", "repository_id": repo_id},
        )
        assert sent.status_code == 200
        assert (repo / "hello.py").read_text(encoding="utf-8") == "new\n"
        before_dash = await http.get("/ops/dashboard", headers=headers)
        assert any(item.get("path") == "hello.py" for item in before_dash.json()["diffs"])

        unauth = await http.post(f"/repositories/{repo_id}/writes/revert", json={"path": "hello.py"})
        assert unauth.status_code == 401

        missing = await http.post(
            "/repositories/repo_missing/writes/revert",
            headers=headers,
            json={"path": "hello.py"},
        )
        assert missing.status_code == 404

        unknown = await http.post(
            f"/repositories/{repo_id}/writes/revert",
            headers=headers,
            json={"path": "nope.py"},
        )
        assert unknown.status_code == 409

        reverted = await http.post(
            f"/repositories/{repo_id}/writes/revert",
            headers=headers,
            json={"path": "hello.py"},
        )
        assert reverted.status_code == 200
        assert (repo / "hello.py").read_text(encoding="utf-8") == "old\n"
        after_dash = await http.get("/ops/dashboard", headers=headers)
        assert not any(item.get("path") == "hello.py" for item in after_dash.json()["diffs"])
    finally:
        await http.aclose()
