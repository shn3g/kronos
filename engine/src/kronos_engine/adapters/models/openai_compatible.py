# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local OpenAI-compatible detection and completions. Never runs repository code."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol
from urllib.parse import urlparse

from kronos_engine.domain.models import assert_cost_allowed, select_completion_model
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult, TokenUsage
from kronos_engine.ports.secrets import ScopedSecret

LOCAL_OPENAI_BASES: tuple[str, ...] = (
    "http://127.0.0.1:11434/v1",
    "http://127.0.0.1:1234/v1",
)


class CompletionCancelled(RuntimeError):
    """Raised when Stop closes an in-flight streamed completion."""

    def __init__(self, partial: str) -> None:
        super().__init__("completion cancelled")
        self.partial = partial


class HttpTransport(Protocol):
    def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]: ...

    def post(
        self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, object]]: ...


@dataclass(frozen=True, slots=True)
class DetectedEndpoint:
    base_url: str
    billed: bool
    models: tuple[str, ...]


class UrllibTransport:
    def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]:
        return _urlopen_json("GET", url, timeout=timeout)

    def post(
        self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, object]]:
        return _urlopen_json("POST", url, timeout=timeout, payload=json, headers=headers)

    def post_sse(
        self,
        url: str,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float,
        cancel: Event,
    ) -> Iterator[str]:
        return _urlopen_sse(url, payload=json, headers=headers, timeout=timeout, cancel=cancel)


def detect_openai_compatible_endpoints(
    *,
    transport: HttpTransport | None = None,
    repo_root: Path | None = None,
) -> tuple[DetectedEndpoint, ...]:
    _ = repo_root
    client = transport or UrllibTransport()
    found: list[DetectedEndpoint] = []
    for base in LOCAL_OPENAI_BASES:
        try:
            status, payload = client.get(f"{base}/models", timeout=0.3)
        except Exception:
            continue
        if status != 200:
            continue
        data = payload.get("data")
        models: list[str] = []
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
            for item in data:
                if isinstance(item, dict):
                    model_id = item.get("id")
                    if isinstance(model_id, str):
                        models.append(model_id)
        found.append(DetectedEndpoint(base_url=base, billed=False, models=tuple(models)))
    return tuple(found)


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        billed: bool,
        transport: HttpTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._billed = billed
        self._transport = transport or UrllibTransport()

    def complete(
        self, request: CompletionRequest, secret: ScopedSecret | None
    ) -> CompletionResult:
        url, headers, body = self._prepare(request, secret, stream=False)
        status, payload = self._transport.post(
            url, body, headers, request.profile.limits.timeout_seconds
        )
        if status != 200:
            raise RuntimeError(f"openai-compatible completion failed: {status}")
        text = _choice_text(payload)
        tokens = _usage_tokens(payload)
        return CompletionResult(text=text, usage=TokenUsage(tokens=tokens))

    def complete_stream(
        self,
        request: CompletionRequest,
        secret: ScopedSecret | None,
        *,
        cancel: Event | None = None,
    ) -> Iterator[str]:
        url, headers, body = self._prepare(request, secret, stream=True)
        cancel_event = cancel or Event()
        poster = getattr(self._transport, "post_sse", None)
        if poster is None:
            stream = _urlopen_sse(
                url,
                payload=body,
                headers=headers,
                timeout=request.profile.limits.timeout_seconds,
                cancel=cancel_event,
            )
        else:
            stream = poster(
                url, body, headers, request.profile.limits.timeout_seconds, cancel_event
            )
        yield from _iter_sse_chunks(stream, cancel_event)

    def _prepare(
        self, request: CompletionRequest, secret: ScopedSecret | None, *, stream: bool
    ) -> tuple[str, dict[str, str], dict[str, object]]:
        _assert_http_url(self._base_url)
        token = secret.require_fresh() if secret is not None else None
        model = select_completion_model(
            request.profile,
            fallback_model_id=request.fallback_model_id,
            fallback_billed=request.fallback_billed,
            provider_billed=self._billed,
        )
        billed = self._billed or request.profile.billed
        assert_cost_allowed(request.profile.limits, estimated_cost=0.0, billed=billed)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        body: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.profile.limits.max_tokens,
        }
        if stream:
            body["stream"] = True
        return f"{self._base_url}/chat/completions", headers, body


def delta_text_from_sse_payload(payload: str) -> str:
    stripped = payload.strip()
    if stripped == "" or stripped == "[DONE]":
        return ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def _iter_sse_chunks(stream: Iterator[str], cancel: Event) -> Iterator[str]:
    partial = ""
    try:
        for payload in stream:
            chunk = delta_text_from_sse_payload(payload)
            if chunk:
                partial += chunk
                yield chunk
            if cancel.is_set():
                raise CompletionCancelled(partial)
    except CompletionCancelled as error:
        raise CompletionCancelled(partial or error.partial) from None


def _assert_http_url(url: str) -> None:
    scheme = urlparse(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("only http and https base URLs are allowed")


def _choice_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def _usage_tokens(payload: dict[str, object]) -> int:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int) and not isinstance(total, bool):
            return total
    return 0


def _urlopen_json(
    method: str,
    url: str,
    *,
    timeout: float,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    _assert_http_url(url)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            parsed: object = json.loads(raw) if raw else {}
            data = parsed if isinstance(parsed, dict) else {}
            return int(response.status), data
    except urllib.error.HTTPError as error:
        return int(error.code), {}
    except OSError:
        return 599, {}


def _urlopen_sse(
    url: str,
    *,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout: float,
    cancel: Event,
) -> Iterator[str]:
    _assert_http_url(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"openai-compatible completion failed: {error.code}") from error
    except OSError as error:
        raise RuntimeError("openai-compatible completion failed: 599") from error
    done = Event()

    def watch() -> None:
        while not done.wait(0.05):
            if cancel.is_set():
                try:
                    response.close()
                except OSError:
                    pass
                return

    threading.Thread(target=watch, daemon=True, name="kronos-sse-cancel").start()
    try:
        yield from _read_sse_data(response, cancel)
    finally:
        done.set()
        try:
            response.close()
        except OSError:
            pass


def _read_sse_data(response: object, cancel: Event) -> Iterator[str]:
    readline = getattr(response, "readline", None)
    if not callable(readline):
        return
    try:
        while True:
            if cancel.is_set():
                raise CompletionCancelled("")
            raw = readline()
            if not raw:
                break
            if isinstance(raw, bytes):
                line = raw.decode("utf-8", errors="replace").strip()
            else:
                line = str(raw).strip()
            if line.startswith("data:"):
                yield line[5:].strip()
    except (OSError, ValueError):
        if cancel.is_set():
            raise CompletionCancelled("") from None
        raise
