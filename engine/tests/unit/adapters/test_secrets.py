# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from kronos_engine.adapters.secrets.os_store import OsSecretStore


def test_os_secret_store_keeps_values_out_of_plaintext_config(tmp_path: Path) -> None:
    config = tmp_path / "config"
    store = OsSecretStore(config)
    store.put("provider:prov_ollama:api_key", "sk-file-secret")
    assert store.get("provider:prov_ollama:api_key") == "sk-file-secret"
    config_text = ""
    for path in config.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".yaml", ".yml", ".toml"}:
            config_text += path.read_text(encoding="utf-8")
    assert "sk-file-secret" not in config_text
