# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.secrets import InMemorySecretStore

from kronos_engine.api.app import create_app
from kronos_engine.application.embedding_install import EmbeddingInstaller
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.state.database import Database


class _QuietDetector:
    def detect(self) -> tuple[object, ...]:
        return ()


class _Handler(BaseHTTPRequestHandler):
    files: dict[str, bytes] = {}

    def do_HEAD(self) -> None:
        path = self.path.split("?", 1)[0]
        body = self.files.get(path, b"")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        body = self.files.get(path, b"")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        _ = format, args


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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wait_until(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for condition")


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, dict[str, str], Path, Settings]]:
    onnx = b"route-onnx"
    tokenizer = b"route-tokenizer"
    _Handler.files = {"/onnx": onnx, "/tokenizer": tokenizer}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://127.0.0.1:{int(port)}"
    settings = _settings(tmp_path)
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    from kronos_engine.application.embedding_install import catalog_entry

    catalog = {
        "minilm-l6-v2": catalog_entry(
            key="minilm-l6-v2",
            dim=384,
            display_name="MiniLM L6 v2",
            document_model_id="all-MiniLM-L6-v2",
            document_filename="all-MiniLM-L6-v2.onnx",
            document_license="Apache-2.0",
            files=(
                (f"{base_url}/onnx", _sha256(onnx), "all-MiniLM-L6-v2.onnx"),
                (f"{base_url}/tokenizer", _sha256(tokenizer), "tokenizer.json"),
            ),
        )
    }
    installer = EmbeddingInstaller(settings.paths.cache / "models", catalog=catalog)
    app = create_app(
        settings,
        database,
        tool_detector=_QuietDetector(),  # type: ignore[arg-type]
        secret_store=InMemorySecretStore(),
        embedding_installer=installer,
    )
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        yield http, headers, tmp_path, settings
    finally:
        await http.aclose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_embedding_install_get_requires_auth(
    client: tuple[AsyncClient, dict[str, str], Path, Settings],
) -> None:
    http, _headers, _tmp, _settings = client
    denied = await http.get("/models/embeddings/install")
    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_embedding_install_routes(
    client: tuple[AsyncClient, dict[str, str], Path, Settings],
) -> None:
    http, headers, tmp_path, settings = client
    initial = await http.get("/models/embeddings/install", headers=headers)
    assert initial.status_code == 200
    payload = initial.json()
    assert "policy" in payload
    assert "SHA-256" in payload["policy"]
    assert any(item["key"] == "minilm-l6-v2" for item in payload["catalog"])

    started = await http.post(
        "/models/embeddings/install",
        headers=headers,
        json={"key": "minilm-l6-v2"},
    )
    assert started.status_code == 200
    _wait_until(
        lambda: (
            (settings.paths.cache / "models" / "minilm-l6-v2" / "all-MiniLM-L6-v2.onnx").is_file()
        )
    )

    removed = await http.delete(
        "/models/embeddings/install",
        headers=headers,
        params={"key": "minilm-l6-v2"},
    )
    assert removed.status_code == 200
    assert not (tmp_path / "cache" / "models" / "minilm-l6-v2").exists()
