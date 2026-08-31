# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local OpenAI-compatible detection and completions. Never runs repository code."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kronos_engine.domain.models import select_completion_model
from kronos_engine.ports.model_provider import CompletionRequest, CompletionResult, TokenUsage
from kronos_engine.ports.secrets import ScopedSecret

LOCAL_OPENAI_BASES: tuple[str, ...] = (
    "http://127.0.0.1:11434/v1",
    "http://127.0.0.1:1234/v1",
)


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
        model = select_completion_model(
            request.profile,
            fallback_model_id=request.fallback_model_id,
            fallback_billed=request.fallback_billed,
        )
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if secret is not None:
            headers["Authorization"] = f"Bearer {secret.value}"
        status, payload = self._transport.post(
            f"{self._base_url}/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": request.prompt}],
                "max_tokens": request.profile.limits.max_tokens,
            },
            headers,
            request.profile.limits.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"openai-compatible completion failed: {status}")
        text = _choice_text(payload)
        tokens = _usage_tokens(payload)
        _ = self._billed
        return CompletionResult(text=text, usage=TokenUsage(tokens=tokens))


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
