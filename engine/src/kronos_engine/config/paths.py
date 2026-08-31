# SPDX-License-Identifier: AGPL-3.0-or-later
"""Platform data, config, cache, and log roots. Never repository-relative by default."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class KronosPaths:
    data: Path
    config: Path
    cache: Path
    logs: Path

    @property
    def database(self) -> Path:
        return self.data / "kronos.sqlite3"

    @property
    def worktrees(self) -> Path:
        return self.cache / "worktrees"

    @property
    def install_state(self) -> Path:
        return self.config / "install.json"


def resolve_paths(
    environ: Mapping[str, str] | None = None,
    *,
    system: str | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> KronosPaths:
    env = os.environ if environ is None else environ
    platform = (system or sys.platform).lower()
    cwd = Path.cwd() if cwd is None else cwd
    home = Path.home() if home is None else home
    _ = cwd  # defaults never use the working tree

    override_data = _optional_path(env, "KRONOS_DATA_HOME")
    override_config = _optional_path(env, "KRONOS_CONFIG_HOME")
    override_cache = _optional_path(env, "KRONOS_CACHE_HOME")
    override_logs = _optional_path(env, "KRONOS_LOG_HOME")
    if override_data and override_config and override_cache and override_logs:
        return KronosPaths(
            data=override_data,
            config=override_config,
            cache=override_cache,
            logs=override_logs,
        )

    defaults = _platform_defaults(platform, env, home)
    return KronosPaths(
        data=override_data or defaults.data,
        config=override_config or defaults.config,
        cache=override_cache or defaults.cache,
        logs=override_logs or defaults.logs,
    )


def _optional_path(env: Mapping[str, str], key: str) -> Path | None:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return None
    return Path(raw)


def _platform_defaults(system: str, env: Mapping[str, str], home: Path) -> KronosPaths:
    if system.startswith("win"):
        local = Path(env.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
        roaming = Path(env.get("APPDATA") or (home / "AppData" / "Roaming"))
        return KronosPaths(
            data=local / "kronos",
            config=roaming / "kronos",
            cache=local / "kronos" / "cache",
            logs=local / "kronos" / "logs",
        )
    if system == "darwin":
        return KronosPaths(
            data=home / "Library" / "Application Support" / "kronos",
            config=home / "Library" / "Application Support" / "kronos",
            cache=home / "Library" / "Caches" / "kronos",
            logs=home / "Library" / "Logs" / "kronos",
        )
    data_home = Path(env.get("XDG_DATA_HOME") or (home / ".local" / "share"))
    config_home = Path(env.get("XDG_CONFIG_HOME") or (home / ".config"))
    cache_home = Path(env.get("XDG_CACHE_HOME") or (home / ".cache"))
    state_home = Path(env.get("XDG_STATE_HOME") or (home / ".local" / "state"))
    return KronosPaths(
        data=data_home / "kronos",
        config=config_home / "kronos",
        cache=cache_home / "kronos",
        logs=state_home / "kronos" / "logs",
    )
