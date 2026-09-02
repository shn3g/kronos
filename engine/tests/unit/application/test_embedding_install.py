# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from kronos_engine.application.embedding_install import (
    EMBEDDING_INSTALL_POLICY,
    EmbeddingInstaller,
    catalog_entry,
    local_adapter_for,
    resolve_local_models_dir,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _FixtureHandler(BaseHTTPRequestHandler):
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


def _fixture_server(files: dict[str, bytes]) -> tuple[str, ThreadingHTTPServer, threading.Thread]:
    _FixtureHandler.files = {path: payload for path, payload in files.items()}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return f"http://127.0.0.1:{int(port)}", server, thread


def _test_catalog(base_url: str, onnx_bytes: bytes, tokenizer_bytes: bytes) -> dict[str, object]:
    onnx_name = "all-MiniLM-L6-v2.onnx"
    return {
        "minilm-l6-v2": catalog_entry(
            key="minilm-l6-v2",
            dim=384,
            display_name="MiniLM L6 v2",
            document_model_id="all-MiniLM-L6-v2",
            document_filename=onnx_name,
            document_license="Apache-2.0",
            files=(
                (f"{base_url}/onnx", _sha256(onnx_bytes), onnx_name),
                (f"{base_url}/tokenizer", _sha256(tokenizer_bytes), "tokenizer.json"),
            ),
        )
    }


def _wait_until(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for condition")


def test_installer_good_checksum_reaches_ready_and_leaves_no_part_files(tmp_path: Path) -> None:
    onnx = b"onnx-fixture-bytes"
    tokenizer = b'{"version":"1.0","model":{"type":"WordPiece"}}'
    base_url, server, thread = _fixture_server(
        {"/onnx": onnx, "/tokenizer": tokenizer},
    )
    try:
        installer = EmbeddingInstaller(
            tmp_path / "models",
            catalog=_test_catalog(base_url, onnx, tokenizer),
        )
        installer.start("minilm-l6-v2")
        _wait_until(lambda: installer.status()["state"] == "ready")
        status = installer.status()
        assert status["state"] == "ready"
        assert status["model_key"] == "minilm-l6-v2"
        assert status["bytes_done"] == status["bytes_total"] == len(onnx) + len(tokenizer)
        model_dir = tmp_path / "models" / "minilm-l6-v2"
        assert (model_dir / "all-MiniLM-L6-v2.onnx").read_bytes() == onnx
        assert (model_dir / "tokenizer.json").read_bytes() == tokenizer
        assert list(model_dir.glob("*.part")) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_installer_bad_checksum_fails_and_removes_partial_files(tmp_path: Path) -> None:
    onnx = b"onnx-fixture-bytes"
    tokenizer = b"tokenizer-fixture"
    base_url, server, thread = _fixture_server(
        {"/onnx": onnx, "/tokenizer": tokenizer},
    )
    catalog = _test_catalog(base_url, onnx, tokenizer)
    entry = catalog["minilm-l6-v2"]
    bad = {
        "minilm-l6-v2": catalog_entry(
            key=entry.key,
            dim=entry.dim,
            display_name=entry.display_name,
            document_model_id=entry.document_model_id,
            document_filename=entry.document_filename,
            document_license=entry.document_license,
            files=(
                (entry.files[0].url, "0" * 64, entry.files[0].dest),
                (entry.files[1].url, entry.files[1].sha256, entry.files[1].dest),
            ),
        )
    }
    try:
        installer = EmbeddingInstaller(tmp_path / "models", catalog=bad)
        installer.start("minilm-l6-v2")
        _wait_until(lambda: installer.status()["state"] == "failed")
        status = installer.status()
        assert status["state"] == "failed"
        model_dir = tmp_path / "models" / "minilm-l6-v2"
        assert not model_dir.exists() or list(model_dir.glob("*")) == []
        assert list((tmp_path / "models").glob("**/*.part")) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_installer_status_transitions(tmp_path: Path) -> None:
    onnx = b"x" * 4096
    tokenizer = b"{}"
    base_url, server, thread = _fixture_server(
        {"/onnx": onnx, "/tokenizer": tokenizer},
    )
    try:
        installer = EmbeddingInstaller(
            tmp_path / "models",
            catalog=_test_catalog(base_url, onnx, tokenizer),
        )
        assert installer.status()["state"] == "idle"
        installer.start("minilm-l6-v2")
        seen: set[str] = set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            seen.add(str(installer.status()["state"]))
            if installer.status()["state"] in {"ready", "failed"}:
                break
            time.sleep(0.001)
        assert "ready" in seen
        assert seen.intersection({"downloading", "verifying", "ready"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_remove_deletes_installed_files(tmp_path: Path) -> None:
    onnx = b"onnx"
    tokenizer = b"tok"
    base_url, server, thread = _fixture_server(
        {"/onnx": onnx, "/tokenizer": tokenizer},
    )
    try:
        installer = EmbeddingInstaller(
            tmp_path / "models",
            catalog=_test_catalog(base_url, onnx, tokenizer),
        )
        installer.start("minilm-l6-v2")
        _wait_until(lambda: installer.status()["state"] == "ready")
        installer.remove("minilm-l6-v2")
        assert not (tmp_path / "models" / "minilm-l6-v2").exists()
        assert installer.is_installed("minilm-l6-v2") is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_resolve_local_models_dir_uses_active_installed_key(tmp_path: Path) -> None:
    root = tmp_path / "models"
    installed = root / "minilm-l6-v2"
    installed.mkdir(parents=True)
    (installed / "all-MiniLM-L6-v2.onnx").write_bytes(b"onnx")
    (installed / "tokenizer.json").write_bytes(b"{}")
    (root / ".active-key").write_text("minilm-l6-v2", encoding="utf-8")
    model_dir, key = resolve_local_models_dir(root)
    assert key == "minilm-l6-v2"
    assert model_dir == installed
    adapter = local_adapter_for(key, model_dir)
    assert adapter is not None


def test_policy_sentence_is_documented() -> None:
    assert "SHA-256" in EMBEDDING_INSTALL_POLICY
    assert "click Install" in EMBEDDING_INSTALL_POLICY
