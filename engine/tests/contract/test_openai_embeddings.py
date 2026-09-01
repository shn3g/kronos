# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI-compatible embeddings contract: local HTTP server only, dense degrades on failure."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kronos_engine.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddingAdapter
from kronos_engine.ports.secrets import ScopedSecret


@contextmanager
def _local_embeddings_server(
    status: int = 200,
    payload: object | None = None,
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    if payload is None:
        payload = {
            "data": [
                {"embedding": [0.25, 0.5, 0.75], "index": 0},
                {"embedding": [1.0, 0.0, 0.0], "index": 1},
            ]
        }
    captured: list[dict[str, object]] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            try:
                body: object = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except json.JSONDecodeError:
                body = raw_body.decode("utf-8", errors="replace")
            captured.append(
                {
                    "path": self.path,
                    "headers": {key: value for key, value in self.headers.items()},
                    "json": body,
                }
            )
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

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


def _embed_payload(payload: object) -> list[list[float]] | None:
    with _local_embeddings_server(payload=payload) as (base_url, _captured):
        adapter = OpenAICompatibleEmbeddingAdapter(
            base_url=base_url,
            model_id="text-embedding-3-small",
            billed=False,
            secret=None,
        )
        try:
            result = adapter.embed(["alpha", "beta"], kind="document")
        except Exception as exc:
            raise AssertionError(f"embed raised {type(exc).__name__}: {exc}") from exc
    if result is None:
        return None
    return [list(row) for row in result]


def test_embed_posts_openai_shape_with_bearer_secret() -> None:
    with _local_embeddings_server() as (base_url, captured):
        adapter = OpenAICompatibleEmbeddingAdapter(
            base_url=base_url,
            model_id="text-embedding-3-small",
            billed=True,
            secret=ScopedSecret(value="sk-live-embed", ttl_seconds=30),
        )
        assert adapter.available("document") is True
        assert adapter.available("code") is True
        vectors = adapter.embed(["alpha", "beta"], kind="document")
        assert vectors == [[0.25, 0.5, 0.75], [1.0, 0.0, 0.0]]
    posted = captured[0]
    assert posted["path"] == "/v1/embeddings"
    assert posted["json"] == {"model": "text-embedding-3-small", "input": ["alpha", "beta"]}
    headers = posted["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer sk-live-embed"


def test_embed_omits_authorization_when_no_secret_and_allows_loopback() -> None:
    payload = {"data": [{"embedding": [0.1, 0.2], "index": 0}]}
    with _local_embeddings_server(payload=payload) as (base_url, captured):
        adapter = OpenAICompatibleEmbeddingAdapter(
            base_url=base_url,
            model_id="nomic-embed-text",
            billed=False,
            secret=None,
        )
        vectors = adapter.embed(["hello"], kind="code")
        assert vectors == [[0.1, 0.2]]
    headers = captured[0]["headers"]
    assert isinstance(headers, dict)
    assert "Authorization" not in headers


def test_http_and_parse_failures_return_none_without_raising() -> None:
    with _local_embeddings_server(status=500, payload={}) as (base_url, _captured):
        failing = OpenAICompatibleEmbeddingAdapter(
            base_url=base_url,
            model_id="text-embedding-3-small",
            billed=True,
            secret=ScopedSecret(value="sk-fail", ttl_seconds=30),
        )
        try:
            assert failing.embed(["hello"], kind="document") is None
        except Exception as exc:
            raise AssertionError(f"embed raised {type(exc).__name__}: {exc}") from exc

    with _local_embeddings_server(payload={"data": "nope"}) as (base_url, _captured):
        malformed = OpenAICompatibleEmbeddingAdapter(
            base_url=base_url,
            model_id="text-embedding-3-small",
            billed=True,
            secret=None,
        )
        try:
            assert malformed.embed(["hello"], kind="document") is None
        except Exception as exc:
            raise AssertionError(f"embed raised {type(exc).__name__}: {exc}") from exc

    closed = OpenAICompatibleEmbeddingAdapter(
        base_url="http://127.0.0.1:1",
        model_id="text-embedding-3-small",
        billed=False,
        secret=None,
    )
    try:
        assert closed.embed(["hello"], kind="document") is None
    except Exception as exc:
        raise AssertionError(f"embed raised {type(exc).__name__}: {exc}") from exc


def test_malformed_base_url_does_not_raise_into_indexer() -> None:
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="http://[",
        model_id="text-embedding-3-small",
        billed=False,
        secret=None,
    )
    try:
        available = adapter.available("document")
        vectors = adapter.embed(["hello"], kind="document")
    except Exception as exc:
        raise AssertionError(
            f"malformed URL raised {type(exc).__name__}: {exc}"
        ) from exc
    assert available is False
    assert vectors is None


def test_malformed_embedding_values_return_none_without_raising() -> None:
    assert _embed_payload(["not", "a", "dict"]) is None
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, float("nan")], "index": 0},
                    {"embedding": [0.0, 1.0], "index": 1},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, float("inf")], "index": 0},
                    {"embedding": [0.0, 1.0], "index": 1},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0], "index": 0},
                    {"embedding": [1.0, 2.0], "index": 1},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, 2.0], "index": 0},
                    {"embedding": [3.0, 4.0], "index": 0},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, 2.0], "index": 0},
                    {"embedding": [3.0, 4.0], "index": 5},
                ]
            }
        )
        is None
    )
