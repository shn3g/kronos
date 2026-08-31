# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer App installation tokens. Never reads GH_TOKEN."""

from __future__ import annotations

import base64
import json
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from kronos_engine.domain.github import REVIEWER_APP_ROLE, REVIEWER_PRIVATE_KEY_REF
from kronos_engine.ports.forge import AppCredentials
from kronos_engine.ports.secrets import ScopedSecret, SecretStore

from kronos_reviewer.http import DEFAULT_TIMEOUT_SECONDS, HttpRequest, HttpTransport


class ReviewerAuthError(RuntimeError):
    """Raised when reviewer credentials are missing or the role is not reviewer."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_app_jwt(app_id: int, pem: str, *, now: int | None = None) -> str:
    issued = int(time.time() if now is None else now)
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps(
            {"iat": issued - 60, "exp": issued + 540, "iss": app_id},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise ReviewerAuthError("GitHub App private key must be RSA")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


class ReviewerAuth:
    def __init__(
        self,
        secrets: SecretStore,
        credentials: AppCredentials,
        transport: HttpTransport,
        *,
        base_url: str = "https://api.github.com",
    ) -> None:
        self._secrets = secrets
        self._credentials = credentials
        self._role = credentials.role
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._cached: ScopedSecret | None = None

    def mint(self) -> ScopedSecret:
        if self._role != REVIEWER_APP_ROLE:
            raise ReviewerAuthError("reviewer auth refuses non-reviewer credentials")
        if self._cached is not None and not self._cached.expired():
            return self._cached
        pem = self._secrets.get(REVIEWER_PRIVATE_KEY_REF)
        if not pem:
            raise ReviewerAuthError("reviewer App private key is missing")
        if self._credentials.installation_id <= 0:
            raise ReviewerAuthError("reviewer App is not installed")
        jwt = build_app_jwt(self._credentials.app_id, pem)
        response = self._transport.send(
            HttpRequest(
                method="POST",
                url=(
                    f"{self._base_url}/app/installations/"
                    f"{self._credentials.installation_id}/access_tokens"
                ),
                headers={
                    "Authorization": f"Bearer {jwt}",
                    "Accept": "application/vnd.github+json",
                },
                body=b"{}",
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        )
        if response.status >= 400:
            raise ReviewerAuthError("reviewer installation token request failed")
        payload = json.loads(response.body.decode() or "{}")
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise ReviewerAuthError("reviewer installation token was empty")
        scoped = ScopedSecret(value=token, ttl_seconds=3600)
        self._cached = scoped
        return scoped
