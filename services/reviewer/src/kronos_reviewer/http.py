# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer-owned HTTP types. No engine adapter imports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout: float


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def send(self, request: HttpRequest) -> HttpResponse: ...


class HttpxTransport:
    def __init__(self, base_url: str = "https://api.github.com") -> None:
        self._base_url = base_url.rstrip("/")

    def send(self, request: HttpRequest) -> HttpResponse:
        import httpx

        url = request.url
        if url.startswith("/"):
            url = f"{self._base_url}{url}"
        with httpx.Client(timeout=request.timeout) as client:
            response = client.request(
                request.method,
                url,
                headers=dict(request.headers),
                content=request.body,
            )
            return HttpResponse(
                status=response.status_code,
                headers={key: value for key, value in response.headers.items()},
                body=response.content,
            )
