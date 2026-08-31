# SPDX-License-Identifier: AGPL-3.0-or-later
"""GitHub HTTP client: pagination, ETags, timeouts, and 403/429/5xx backoff."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urlparse

from kronos_engine.ports.forge import (
    ForgePermissionDenied,
    ForgeRateLimited,
    ForgeTransientError,
    IdempotencyKey,
    provenance_marker,
)

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 4
PAGE_SIZE = 10


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


def next_link(headers: Mapping[str, str]) -> str | None:
    raw = headers.get("Link") or headers.get("link")
    if not raw:
        return None
    for part in raw.split(","):
        if 'rel="next"' in part:
            start = part.find("<")
            end = part.find(">")
            if start >= 0 and end > start:
                return part[start + 1 : end]
    return None


def is_rate_limited(status: int, headers: Mapping[str, str]) -> bool:
    if status == 429:
        return True
    if status == 403:
        remaining = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        return remaining == "0"
    return False


class GitHubClient:
    def __init__(
        self,
        transport: HttpTransport,
        auth: object,
        *,
        role: str = "controller",
        sleep: Callable[[float], None] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
        base_url: str = "https://api.github.com",
    ) -> None:
        self._transport = transport
        self._auth = auth
        self._role = role
        self._sleep = sleep or time.sleep
        self.timeout = timeout
        self._max_retries = max_retries
        self._base_url = base_url.rstrip("/")
        self._etags: dict[str, str] = {}
        self._list_cache: dict[str, list[object]] = {}
        self.audit_log: list[str] = []

    def url(self, path: str, params: Mapping[str, str | int] | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            target = path
        else:
            target = f"{self._base_url}{path}"
        if params:
            query = urlencode({key: str(value) for key, value in params.items()})
            sep = "&" if urlparse(target).query else "?"
            return f"{target}{sep}{query}"
        return target

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, object] | None = None,
        params: Mapping[str, str | int] | None = None,
        use_jwt: bool = False,
    ) -> HttpResponse:
        url = self.url(path, params)
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        headers["Authorization"] = f"Bearer {self._authorization(use_jwt=use_jwt)}"
        cache_key = self._cache_key(method, url)
        if method == "GET" and cache_key in self._etags:
            headers["If-None-Match"] = self._etags[cache_key]
        body = json.dumps(json_body).encode() if json_body is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            response = self._transport.send(
                HttpRequest(
                    method=method,
                    url=url,
                    headers=headers,
                    body=body,
                    timeout=self.timeout,
                )
            )
            self.audit_log.append(f"{method} {urlparse(url).path} auth=redacted")
            if response.status == 304 or response.status < 400:
                etag = response.headers.get("ETag") or response.headers.get("etag")
                if etag and method == "GET":
                    self._etags[cache_key] = etag
                return response
            if is_rate_limited(response.status, response.headers):
                last_error = ForgeRateLimited("GitHub rate limited the request")
                self._sleep(0.0)
                continue
            if response.status in {500, 502, 503, 504}:
                last_error = ForgeTransientError("GitHub returned a transient error")
                self._sleep(0.0)
                continue
            if response.status in {401, 403}:
                raise ForgePermissionDenied("GitHub denied the request")
            raise ForgeTransientError(f"GitHub request failed: {response.status}")
        if isinstance(last_error, ForgeRateLimited):
            raise last_error
        raise last_error or ForgeTransientError("GitHub request failed")

    def request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, object] | None = None,
        params: Mapping[str, str | int] | None = None,
        use_jwt: bool = False,
    ) -> object:
        response = self.request(
            method, path, json_body=json_body, params=params, use_jwt=use_jwt
        )
        if response.status == 304:
            return self._list_cache.get(self._cache_key(method, self.url(path, params)), [])
        if not response.body:
            return {}
        return json.loads(response.body.decode())

    def paginate(
        self,
        path: str,
        *,
        params: MutableMapping[str, str | int] | None = None,
    ) -> list[object]:
        query: dict[str, str | int] = dict(params or {})
        query.setdefault("per_page", PAGE_SIZE)
        first_url = self.url(path, query)
        cache_key = self._cache_key("GET", first_url)
        items: list[object] = []
        url: str | None = path
        current_params: Mapping[str, str | int] | None = query
        while url:
            response = self.request("GET", url, params=current_params)
            if response.status == 304:
                cached = self._list_cache.get(cache_key)
                return list(cached) if cached is not None else []
            payload = json.loads(response.body.decode() or "[]")
            if isinstance(payload, list):
                items.extend(payload)
            url = next_link(response.headers)
            current_params = None
        self._list_cache[cache_key] = items
        return items

    def _authorization(self, *, use_jwt: bool) -> str:
        mint = getattr(self._auth, "mint")
        jwt_for = getattr(self._auth, "jwt_for", None)
        if use_jwt and jwt_for is not None:
            token = jwt_for(self._role)
            if isinstance(token, str):
                return token
        scoped = mint(self._role)
        return str(scoped.require_fresh())

    def _cache_key(self, method: str, url: str) -> str:
        parsed = urlparse(url)
        return f"{method}:{parsed.path}"


def marker_in(text: str | None, key: IdempotencyKey) -> bool:
    return text is not None and provenance_marker(key) in text
