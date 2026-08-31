# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install, upgrade, incompatible refusal, and rollback without live machines."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.version import client_is_compatible


class IncompatibleVersion(RuntimeError):
    """Raised when a client cannot use the target engine version."""


@dataclass(frozen=True, slots=True)
class InstallState:
    version: str
    engine_version: str
    previous_version: str | None = None


def install(target: Path, *, version: str, engine_version: str) -> InstallState:
    current = target / "current"
    current.mkdir(parents=True, exist_ok=True)
    _write_version(current / "version.json", version=version, engine_version=engine_version)
    return InstallState(version=version, engine_version=engine_version)


def upgrade(
    target: Path,
    *,
    to_version: str,
    engine_version: str,
    min_client_version: str,
    client_version: str,
) -> InstallState:
    if not client_is_compatible(client_version, min_client_version, engine_version):
        raise IncompatibleVersion(
            f"desktop {client_version} cannot use engine {engine_version}"
        )
    current = target / "current"
    previous = target / "previous"
    if not (current / "version.json").is_file():
        raise IncompatibleVersion("no installed version to upgrade")
    old = _read_version(current / "version.json")
    if previous.exists():
        shutil.rmtree(previous)
    current.rename(previous)
    current.mkdir(parents=True, exist_ok=True)
    _write_version(current / "version.json", version=to_version, engine_version=engine_version)
    return InstallState(
        version=to_version,
        engine_version=engine_version,
        previous_version=str(old["version"]),
    )


def rollback(target: Path) -> InstallState:
    current = target / "current"
    previous = target / "previous"
    if not (previous / "version.json").is_file():
        payload = _read_version(current / "version.json")
        return InstallState(
            version=str(payload["version"]),
            engine_version=str(payload["engine_version"]),
        )
    staging = target / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    current.rename(staging)
    previous.rename(current)
    staging.rename(previous)
    payload = _read_version(current / "version.json")
    prev = _read_version(previous / "version.json")
    return InstallState(
        version=str(payload["version"]),
        engine_version=str(payload["engine_version"]),
        previous_version=str(prev["version"]),
    )


def _write_version(path: Path, *, version: str, engine_version: str) -> None:
    path.write_text(
        json.dumps({"version": version, "engine_version": engine_version}, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_version(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("version.json must be an object")
    return {str(key): value for key, value in payload.items()}

