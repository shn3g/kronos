# SPDX-License-Identifier: AGPL-3.0-or-later
"""OS credential storage via Windows Credential Manager, macOS Keychain, or libsecret."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


class SecretStoreError(RuntimeError):
    """Raised when the OS credential backend is missing or insecure."""


class KeyringBackend(Protocol):
    def set_password(self, service: str, username: str, password: str) -> None: ...

    def get_password(self, service: str, username: str) -> str | None: ...

    def delete_password(self, service: str, username: str) -> None: ...


SERVICE = "kronos.engine"


class OsSecretStore:
    def __init__(self, config_root: Path, *, backend: KeyringBackend | None = None) -> None:
        _ = config_root
        self._backend = backend

    def put(self, name: str, value: str) -> None:
        backend = self._resolved_backend()
        try:
            backend.set_password(SERVICE, name, value)
        except KeyringError as error:
            raise SecretStoreError("OS credential storage rejected the secret") from error

    def get(self, name: str) -> str | None:
        backend = self._resolved_backend()
        try:
            return backend.get_password(SERVICE, name)
        except KeyringError as error:
            raise SecretStoreError("OS credential storage could not read the secret") from error

    def delete(self, name: str) -> None:
        backend = self._resolved_backend()
        try:
            backend.delete_password(SERVICE, name)
        except PasswordDeleteError:
            return
        except KeyringError as error:
            raise SecretStoreError("OS credential storage could not delete the secret") from error

    def _resolved_backend(self) -> KeyringBackend:
        backend: KeyringBackend = self._backend or keyring.get_keyring()
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
