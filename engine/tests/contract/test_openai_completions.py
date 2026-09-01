# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI-compatible completions: messages array and SSE streaming against a local server."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kronos_engine.adapters.models.openai_compatible import OpenAICompatibleProvider
from kronos_engine.domain.models import ModelProfile, ResourceLimits
from kronos_engine.ports.model_provider import CompletionRequest
from kronos_engine.ports.secrets import ScopedSecret


@contextmanager
def _local_chat_server(
    *,
    status: int = 200,
    payload: object | None = None,
    stream_chunks: tuple[str, ...] | None = None,
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    if payload is None:
        payload = {
            "choices": [{"message": {"content": "planned"}}],
            "usage": {"total_tokens": 4},
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
            stream = isinstance(body, dict) and body.get("stream") is True
            if stream and stream_chunks is not None and status == 200:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in stream_chunks:
                    event = json.dumps({"choices": [{"delta": {"content": chunk}}]})
                    self.wfile.write(f"data: {event}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                return
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


def _profile() -> ModelProfile:
    return ModelProfile(
        id="prof_planner",
        display_name="Local planner",
        role="planner",
        provider_id="prov_ollama",
        model_id="llama3",
        billed=False,
        approved_fallbacks=(),
        limits=ResourceLimits(
            max_tokens=128,
            max_attempts=3,
            timeout_seconds=15.0,
            cost_ceiling=0.0,
        ),
    )


def test_complete_posts_messages_array_when_provided() -> None:
    messages = (
        {"role": "system", "content": "return json"},
        {"role": "user", "content": "plan this goal"},
    )
    with _local_chat_server() as (base_url, captured):
        provider = OpenAICompatibleProvider(base_url=base_url, billed=False)
        result = provider.complete(
            CompletionRequest(profile=_profile(), prompt="ignored", messages=messages),
            secret=ScopedSecret(value="sk-msg", ttl_seconds=30),
        )
        assert result.text == "planned"
    posted = captured[0]
    assert posted["path"] == "/v1/chat/completions"
    body = posted["json"]
    assert isinstance(body, dict)
    assert body["messages"] == list(messages)
    assert body.get("stream") is not True
    headers = posted["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer sk-msg"


def test_complete_uses_prompt_as_single_user_message_when_messages_omitted() -> None:
    with _local_chat_server() as (base_url, captured):
        provider = OpenAICompatibleProvider(base_url=base_url, billed=False)
        result = provider.complete(
            CompletionRequest(profile=_profile(), prompt="hello"),
            secret=None,
        )
        assert result.text == "planned"
    body = captured[0]["json"]
    assert isinstance(body, dict)
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_stream_yields_sse_delta_chunks() -> None:
    with _local_chat_server(stream_chunks=("Hel", "lo")) as (base_url, captured):
        provider = OpenAICompatibleProvider(base_url=base_url, billed=False)
        chunks = list(
            provider.stream(
                CompletionRequest(profile=_profile(), prompt="hello"),
                secret=ScopedSecret(value="sk-stream", ttl_seconds=30),
            )
        )
        assert chunks == ["Hel", "lo"]
    posted = captured[0]
    assert posted["path"] == "/v1/chat/completions"
    body = posted["json"]
    assert isinstance(body, dict)
    assert body["stream"] is True
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    headers = posted["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer sk-stream"


def test_stream_http_error_fails_closed_without_hanging() -> None:
    with _local_chat_server(status=500, payload={}) as (base_url, _captured):
        provider = OpenAICompatibleProvider(base_url=base_url, billed=False)
        try:
            list(
                provider.stream(
                    CompletionRequest(profile=_profile(), prompt="hello"),
                    secret=None,
                )
            )
        except RuntimeError as error:
            assert "500" in str(error)
        else:
            raise AssertionError("stream must fail closed on HTTP errors")
