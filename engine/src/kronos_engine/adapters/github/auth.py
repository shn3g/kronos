# SPDX-License-Identifier: AGPL-3.0-or-later
"""GitHub App JWT and short-lived installation tokens. Keys stay in SecretStore."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from kronos_engine.domain.github import (
    APP_ROLES,
    CONTROLLER_PRIVATE_KEY_REF,
    REVIEWER_PRIVATE_KEY_REF,
)
from kronos_engine.ports.forge import AppCredentials, ForgeAuthError
from kronos_engine.ports.secrets import ScopedSecret, SecretStore

if TYPE_CHECKING:
    from kronos_engine.adapters.github.client import HttpTransport

KEY_REFS = {
    "controller": CONTROLLER_PRIVATE_KEY_REF,
    "reviewer": REVIEWER_PRIVATE_KEY_REF,
}


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
        raise ForgeAuthError("GitHub App private key must be RSA")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


class InstallationAuth:
    """Mints installation tokens from App private keys. Never reads GH_TOKEN."""

    def __init__(
        self,
        secrets: SecretStore,
        apps: Mapping[str, AppCredentials],
        transport: HttpTransport,
        *,
        sleep: Callable[[float], None] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._secrets = secrets
        self._apps = dict(apps)
        self._transport = transport
        self._sleep = sleep or time.sleep
        self._now = now or time.time
        self._cached: dict[str, ScopedSecret] = {}

    def mint(self, role: str) -> ScopedSecret:
        if role not in APP_ROLES:
            raise ForgeAuthError(f"unknown GitHub App role: {role}")
        cached = self._cached.get(role)
        if cached is not None and not cached.expired():
            return cached
        pem = self._secrets.get(KEY_REFS[role])
        if not pem:
            raise ForgeAuthError(f"{role} App private key is missing")
        creds = self._apps.get(role)
        if creds is None or creds.installation_id <= 0:
            raise ForgeAuthError(f"{role} App is not installed")
        jwt = build_app_jwt(creds.app_id, pem, now=int(self._now()))
        from kronos_engine.adapters.github.client import HttpRequest

        response = self._transport.send(
            HttpRequest(
                method="POST",
                url=(
                    "https://api.github.com/app/installations/"
                    f"{creds.installation_id}/access_tokens"
                ),
                headers={
                    "Authorization": f"Bearer {jwt}",
                    "Accept": "application/vnd.github+json",
                },
                body=b"{}",
                timeout=30.0,
            )
        )
        if response.status >= 400:
            raise ForgeAuthError(f"{role} installation token request failed")
        payload = json.loads(response.body.decode() or "{}")
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise ForgeAuthError(f"{role} installation token was empty")
        scoped = ScopedSecret(value=token, ttl_seconds=3600)
        self._cached[role] = scoped
        return scoped

    def jwt_for(self, role: str) -> str:
        pem = self._secrets.get(KEY_REFS[role])
        if not pem:
            raise ForgeAuthError(f"{role} App private key is missing")
        creds = self._apps.get(role)
        if creds is None:
            raise ForgeAuthError(f"{role} App is not registered")
        return build_app_jwt(creds.app_id, pem, now=int(self._now()))
