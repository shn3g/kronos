# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

from kronos_engine.config.paths import KronosPaths
from kronos_engine.config.ready_file import write_engine_ready


def test_write_engine_ready_records_loopback_url_without_the_token(tmp_path: Path) -> None:
    paths = KronosPaths(
        data=tmp_path / "data",
        config=tmp_path / "config",
        cache=tmp_path / "cache",
        logs=tmp_path / "logs",
    )

    dest = write_engine_ready(paths, "http://127.0.0.1:7431")

    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload == {"base_url": "http://127.0.0.1:7431"}
    assert "token" not in json.dumps(payload)
    assert dest == tmp_path / "config" / "engine_ready.json"
