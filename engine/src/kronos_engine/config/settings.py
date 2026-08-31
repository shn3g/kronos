# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine process settings. FastAPI does not live here."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from kronos_engine import __version__
from kronos_engine.config.paths import KronosPaths, resolve_paths

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
CLIENT_VERSION_HEADER = "X-Kronos-Client-Version"


@dataclass(frozen=True, slots=True)
class Settings:
    engine_version: str
    min_client_version: str
    bind_host: str
    bind_port: int
    auth_token: str
    paths: KronosPaths

    def __post_init__(self) -> None:
        if self.bind_host not in LOOPBACK_HOSTS:
            raise ValueError("engine must bind loopback")
        if self.auth_token.strip() == "":
            raise ValueError("auth token is required")
        if self.bind_port < 0:
            raise ValueError("bind port must be >= 0")


def is_loopback_client(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    paths = resolve_paths(env)
    token = env.get("KRONOS_AUTH_TOKEN") or _read_or_create_token(paths)
    return Settings(
        engine_version=env.get("KRONOS_ENGINE_VERSION") or __version__,
        min_client_version=env.get("KRONOS_MIN_CLIENT_VERSION") or "0.1.0",
        bind_host=env.get("KRONOS_BIND_HOST") or "127.0.0.1",
        bind_port=int(env.get("KRONOS_BIND_PORT") or "0"),
        auth_token=token,
        paths=paths,
    )


def _read_or_create_token(paths: KronosPaths) -> str:
    path = paths.install_state
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        token = payload.get("auth_token")
        if isinstance(token, str) and token.strip() != "":
            return token
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"auth_token": token}), encoding="utf-8")
    return token
