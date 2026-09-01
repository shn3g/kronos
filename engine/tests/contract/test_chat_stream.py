# SPDX-License-Identifier: AGPL-3.0-or-later
"""ChatService streams orchestrator tokens against a fake local HTTP server."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.application.chat import ChatService, ChatTurn
from kronos_engine.application.goals import GoalService
from kronos_engine.application.model_profiles import ModelProfileService, ProviderDraft
from kronos_engine.application.planning import PlanningService
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.paths import resolve_paths
from kronos_engine.domain.models import MODEL_ROLES, ModelProfile, ResourceLimits
from kronos_engine.indexing.context import ContextPack
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.model_profiles import SqliteModelRegistry
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry


@contextmanager
def _local_chat_server(
    *, stream_chunks: tuple[str, ...]
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    captured: list[dict[str, object]] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            body: object = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            captured.append(
                {
                    "path": self.path,
                    "json": body,
                    "headers": {key: value for key, value in self.headers.items()},
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in stream_chunks:
                event = json.dumps({"choices": [{"delta": {"content": chunk}}]})
                self.wfile.write(f"data: {event}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, format: str, *args: object) -> None:
            _ = format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _host, port = server.server_address
        yield f"http://127.0.0.1:{int(port)}/v1", captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class _Indexer:
    def search(
        self,
        repo_id: str,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 20,
        budget_tokens: int = 4000,
    ) -> ContextPack:
        _ = repo_id, query, mode, limit, budget_tokens
        return ContextPack(items=())


class _Planner:
    def plan(self, goal: object) -> dict[str, object]:
        _ = goal
        raise RuntimeError("planner should not run for answers")


def test_chat_streams_orchestrator_tokens_from_local_provider(tmp_path: Path) -> None:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    database = Database(paths.database)
    conn = database.connect()
    secrets = InMemorySecretStore()
    registry = SqliteModelRegistry(conn)
    models = ModelProfileService(registry, secrets)
    repos = RepositoryService(
        SqliteRepositoryRegistry(conn),
        paths,
        FilesystemGitInspector(),
        ManifestStackDetector(),
        CacheRuntimeLayout(),
    )
    root = init_git_repo(tmp_path / "alpha", files={"README.md": "alpha\n"})
    enrolled = repos.enrol(str(root))
    recorder = Recorder(conn, SqliteEventStore(conn), SqliteOutbox(conn))
    goals = GoalService(SqliteGoalStore(conn), repos, recorder)
    planning = PlanningService(SqliteGoalStore(conn), repos, recorder, _Planner())

    with _local_chat_server(stream_chunks=("Hel", "lo")) as (base_url, captured):
        provider = models.register_provider(
            ProviderDraft(
                kind="openai_compatible",
                display_name="Fake",
                base_url=base_url,
                billed=False,
                api_key="sk-stream",
            )
        )
        for item in models.list_profiles():
            models.save_profile(
                ModelProfile(
                    id=item.id,
                    display_name=item.display_name,
                    role=item.role,
                    provider_id=provider.id,
                    model_id="stream-chat",
                    billed=False,
                    approved_fallbacks=(),
                    limits=ResourceLimits(
                        max_tokens=4096,
                        max_attempts=3,
                        timeout_seconds=15.0,
                        cost_ceiling=0.0,
                    ),
                )
            )
        models.assign({role: f"prof_{provider.id}_{role}" for role in MODEL_ROLES})
        chat = ChatService(
            conn,
            repos,
            goals,
            planning,
            _Indexer(),  # type: ignore[arg-type]
            registry,
            secrets,
            SqliteEventStore(conn),
        )
        conversation = chat.create_conversation(enrolled.id.value)
        tokens: list[str] = []
        final: ChatTurn | None = None
        for item in chat.stream_message(conversation.id, "Say hello"):
            if isinstance(item, str):
                tokens.append(item)
            else:
                final = item
        assert "".join(tokens) == "Hello"
        assert tokens == ["Hel", "lo"]
        assert final is not None
        assert final.content == "Hello"
        assert final.goal_refs == ()
        assert captured
        body = captured[0]["json"]
        assert isinstance(body, dict)
        assert body.get("stream") is True
        assert int(body["max_tokens"]) <= 1024
        headers = captured[0]["headers"]
        assert isinstance(headers, dict)
        assert headers.get("Authorization") == "Bearer sk-stream"
        stored = chat.get_conversation(conversation.id)
        roles = [message.role for message in stored.messages]
        assert "user" in roles
        assert "assistant" in roles
