# SPDX-License-Identifier: AGPL-3.0-or-later
"""OS credential storage via Windows Credential Manager, macOS Keychain, or libsecret."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


class SecretStoreError(RuntimeError):
    """Raised when the OS credential backend is missing, insecure, or unresponsive."""


class KeyringBackend(Protocol):
    def set_password(self, service: str, username: str, password: str) -> None: ...

    def get_password(self, service: str, username: str) -> str | None: ...

    def delete_password(self, service: str, username: str) -> None: ...


SERVICE = "kronos.engine"

# Headless D-Bus SecretService can block keyring calls forever; never let that hang a request.
KEYRING_TIMEOUT_SECONDS = 5.0
_TIMEOUT_MESSAGE = "The system credential store did not respond. Kronos could not save the key."


def _call_with_timeout(fn: Callable[..., Any], *args: Any) -> Any:
    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["value"] = fn(*args)
        except BaseException as error:  # re-raised on the caller thread below
            result["error"] = error

    worker = threading.Thread(target=run, daemon=True, name="kronos-keyring")
    worker.start()
    worker.join(KEYRING_TIMEOUT_SECONDS)
    if worker.is_alive():
        raise SecretStoreError(_TIMEOUT_MESSAGE)
    if "error" in result:
        raise result["error"]
    return result.get("value")


class OsSecretStore:
    def __init__(self, config_root: Path, *, backend: KeyringBackend | None = None) -> None:
        _ = config_root
        self._backend = backend

    def put(self, name: str, value: str) -> None:
        backend = self._resolved_backend()
        try:
            _call_with_timeout(backend.set_password, SERVICE, name, value)
        except KeyringError as error:
            raise SecretStoreError("OS credential storage rejected the secret") from error

    def get(self, name: str) -> str | None:
        backend = self._resolved_backend()
        try:
            value = _call_with_timeout(backend.get_password, SERVICE, name)
        except KeyringError as error:
            raise SecretStoreError("OS credential storage could not read the secret") from error
        return value if isinstance(value, str) else None

    def delete(self, name: str) -> None:
        backend = self._resolved_backend()
        try:
            _call_with_timeout(backend.delete_password, SERVICE, name)
        except PasswordDeleteError:
            return
        except KeyringError as error:
            raise SecretStoreError("OS credential storage could not delete the secret") from error

    def _resolved_backend(self) -> KeyringBackend:
        backend = self._backend
        if backend is None:
            resolved: KeyringBackend = _call_with_timeout(keyring.get_keyring)
            self._backend = backend = resolved
        if _is_insecure_backend(backend):
            raise SecretStoreError(
                "refusing plaintext file or missing OS credential keyring backend"
            )
        return backend


def _is_insecure_backend(backend: object) -> bool:
    name = str(getattr(backend, "name", "")).lower()
    module = type(backend).__module__.lower()
    type_name = type(backend).__name__.lower()
    tokens = f"{name} {module} {type_name}"
    return any(flag in tokens for flag in ("file", "plain", "fail", "null"))
