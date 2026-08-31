# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import stat
from pathlib import Path

import pytest
from tests.support.secrets import MemoryKeyring

from kronos_engine.adapters.secrets.os_store import OsSecretStore, SecretStoreError
from kronos_engine.ports.secrets import ScopedSecret, SecretExpiredError


def test_os_secret_store_backing_store_is_not_a_world_readable_file(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    backend = MemoryKeyring()
    store = OsSecretStore(config, backend=backend)
    store.put("provider:prov_ollama:api_key", "sk-file-secret")
    assert store.get("provider:prov_ollama:api_key") == "sk-file-secret"
    leaked: list[Path] = []
    for path in config.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "sk-file-secret" in text:
            leaked.append(path)
        mode = path.stat().st_mode
        assert mode & stat.S_IROTH == 0
        assert mode & stat.S_IWOTH == 0
    assert leaked == []
    assert backend.get_password("kronos.engine", "provider:prov_ollama:api_key") == "sk-file-secret"


def test_os_secret_store_refuses_plaintext_file_backend(tmp_path: Path) -> None:
    class _PlainFileBackend:
        def set_password(self, service: str, username: str, password: str) -> None:
            (tmp_path / "world.txt").write_text(
                f"{service}:{username}:{password}", encoding="utf-8"
            )

        def get_password(self, service: str, username: str) -> str | None:
            _ = service
            _ = username
            return None

        def delete_password(self, service: str, username: str) -> None:
            _ = service
            _ = username

        @property
        def name(self) -> str:
            return "file"

    store = OsSecretStore(tmp_path / "config", backend=_PlainFileBackend())
    with pytest.raises(SecretStoreError, match="credential|OS|keyring|file"):
        store.put("provider:x:api_key", "sk-nope")
    assert not (tmp_path / "world.txt").exists()


def test_scoped_secret_expires_after_ttl() -> None:
    secret = ScopedSecret(value="sk-live", ttl_seconds=30, issued_at=100.0)
    assert secret.expired(now=100.0) is False
    assert secret.expired(now=129.9) is False
    assert secret.expired(now=130.0) is True
    with pytest.raises(SecretExpiredError):
        secret.require_fresh(now=131.0)
