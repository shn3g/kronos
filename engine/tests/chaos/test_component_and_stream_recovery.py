# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine chaos recovery: background worker loss and interrupted chat streams."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.secrets import InMemorySecretStore

from kronos_engine.api.app import create_app
from kronos_engine.application.chat import request_cancel
from kronos_engine.application.component_supervisor import ComponentSupervisor
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.ports.model_provider import CompletionRequest
from kronos_engine.state.database import Database


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


class _KillableWorker:
    def __init__(self) -> None:
        self.starts = 0
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.starts += 1
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def kill(self) -> None:
        self.stop()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        assert self._stop is not None
        self._stop.wait()


@pytest.mark.asyncio
async def test_supervisor_restarts_killed_index_worker_while_chat_and_health_remain_available(
    tmp_path: Path,
) -> None:
    app = create_app(
        _settings(tmp_path),
        Database(tmp_path / "data" / "kronos.sqlite3"),
        secret_store=InMemorySecretStore(),
    )
    supervisor = app.state.component_supervisor
    assert isinstance(supervisor, ComponentSupervisor)
    worker = _KillableWorker()
    supervisor.register(
        "index", start=worker.start, stop=worker.stop, is_alive=worker.is_alive
    )
    supervisor.start("index")
    worker.kill()
    assert worker.is_alive() is False

    supervisor.supervise_once()

    status = supervisor.status("index")[0]
    assert worker.starts == 2
    assert status.alive is True
    assert status.restarts == 1

    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        health = await http.get("/health", headers=headers)
        conversation = await http.post("/conversations", json={}, headers=headers)
    finally:
        await http.aclose()
        supervisor.stop("index")

    assert health.status_code == 200
    assert conversation.status_code == 200


async def _assign_orchestrator(http: AsyncClient, headers: dict[str, str]) -> None:
    provider = await http.post(
        "/models/providers",
        headers=headers,
        json={
            "kind": "openai_compatible",
            "display_name": "Chaos fixture",
            "base_url": "http://127.0.0.1:11434/v1",
            "billed": False,
            "api_key": "sk-chaos",
        },
    )
    assert provider.status_code == 200
    profiles = {item["role"]: item["id"] for item in provider.json()["profiles"]}
    assigned = await http.put("/models/assignments", headers=headers, json=profiles)
    assert assigned.status_code == 200


@pytest.mark.asyncio
async def test_cancelled_chat_stream_recovers_for_the_next_request(tmp_path: Path) -> None:
    conversation_ids: list[str] = []
    turns = 0

    def stream(_request: CompletionRequest, _secret: object) -> Iterator[str]:
        nonlocal turns
        turns += 1
        yield "partial"
        if turns == 1:
            request_cancel(conversation_ids[0])
            yield " ignored"
        else:
            yield " response"

    app = create_app(
        _settings(tmp_path),
        Database(tmp_path / "data" / "kronos.sqlite3"),
        secret_store=InMemorySecretStore(),
        chat_stream=stream,
    )
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        created = await http.post("/conversations", json={}, headers=headers)
        assert created.status_code == 200
        conversation_id = str(created.json()["id"])
        conversation_ids.append(conversation_id)
        await _assign_orchestrator(http, headers)

        interrupted = await http.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": "Start a stream"},
            headers=headers,
        )
        recovered = await http.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": "Try again"},
            headers=headers,
        )
    finally:
        await http.aclose()

    assert "Stopped. Ask again" in interrupted.text
    assert '"content": "partial response"' in recovered.text
    assert turns == 2
