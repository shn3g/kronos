# SPDX-License-Identifier: AGPL-3.0-or-later
"""Owner-only credential files. Values never go in provider JSON or SQLite."""

from __future__ import annotations

from pathlib import Path


class OsSecretStore:
    def __init__(self, config_root: Path) -> None:
        self._root = config_root / "secrets"
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, name: str, value: str) -> None:
        path = self._path(name)
        path.write_text(value, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def get(self, name: str) -> str | None:
        path = self._path(name)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.is_file():
            path.unlink()

    def _path(self, name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        return self._root / safe
