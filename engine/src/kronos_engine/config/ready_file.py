# SPDX-License-Identifier: AGPL-3.0-or-later
"""Loopback URL for the Vite web preview. Never includes the auth token."""

from __future__ import annotations

import json
from pathlib import Path

from kronos_engine.config.paths import KronosPaths

READY_FILE_NAME = "engine_ready.json"


def write_engine_ready(paths: KronosPaths, ready_url: str) -> Path:
    dest = paths.config / READY_FILE_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"base_url": ready_url}), encoding="utf-8")
    return dest
