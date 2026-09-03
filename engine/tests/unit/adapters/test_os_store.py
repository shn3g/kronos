# SPDX-License-Identifier: AGPL-3.0-or-later
"""OS secret store never blocks the engine when the keyring hangs."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from tests.support.secrets import MemoryKeyring

from kronos_engine.adapters.secrets import os_store
from kronos_engine.adapters.secrets.os_store import OsSecretStore, SecretStoreError


class _HangingBackend:
    def set_password(self, service: str, username: str, password: str) -> None:
        time.sleep(60)

    def get_password(self, service: str, username: str) -> str | None:
        time.sleep(60)
        return None

    def delete_password(self, service: str, username: str) -> None:
        time.sleep(60)


def test_put_times_out_with_plain_english_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os_store, "KEYRING_TIMEOUT_SECONDS", 0.2)
    store = OsSecretStore(tmp_path / "config", backend=_HangingBackend())
    started = time.monotonic()
    with pytest.raises(SecretStoreError, match="did not respond"):
        store.put("provider:x:api_key", "sk-test")
    assert time.monotonic() - started < 2.0


def test_get_times_out_and_does_not_leak_non_daemon_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os_store, "KEYRING_TIMEOUT_SECONDS", 0.2)
    store = OsSecretStore(tmp_path / "config", backend=_HangingBackend())
    with pytest.raises(SecretStoreError, match="did not respond"):
        store.get("provider:x:api_key")
    assert all(t.daemon for t in threading.enumerate() if t.name.startswith("kronos-keyring"))


def test_delete_times_out_with_plain_english_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os_store, "KEYRING_TIMEOUT_SECONDS", 0.2)
    store = OsSecretStore(tmp_path / "config", backend=_HangingBackend())
    with pytest.raises(SecretStoreError, match="did not respond"):
        store.delete("provider:x:api_key")


def test_hanging_keyring_resolution_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hanging_get_keyring() -> object:
        time.sleep(60)
        return MemoryKeyring()

    monkeypatch.setattr(os_store, "KEYRING_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(os_store.keyring, "get_keyring", hanging_get_keyring)
    store = OsSecretStore(tmp_path / "config")
    with pytest.raises(SecretStoreError, match="did not respond"):
        store.get("provider:x:api_key")


def test_resolved_keyring_backend_is_cached_after_first_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    backend = MemoryKeyring()

    def counting_get_keyring() -> object:
        nonlocal calls
        calls += 1
        return backend

    monkeypatch.setattr(os_store.keyring, "get_keyring", counting_get_keyring)
    store = OsSecretStore(tmp_path / "config")
    store.put("provider:x:api_key", "sk-test")
    assert store.get("provider:x:api_key") == "sk-test"
    store.delete("provider:x:api_key")
    assert store.get("provider:x:api_key") is None
    assert calls == 1
