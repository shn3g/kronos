# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local metrics and optional OpenTelemetry/Langfuse export. Off by default."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from kronos_engine.observability.redaction import redact_mapping, redact_text

_DEFAULT_MAX_LOCAL_BYTES = 2_000_000


def export_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get("KRONOS_OTEL_EXPORT", "").strip() == "1"


class LocalMetrics:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def inc(self, name: str, amount: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + amount

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)


class Tracer:
    def __init__(
        self,
        destination: Path | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        otel_export: bool = False,
        langfuse_export: bool = False,
        export_sink: Path | None = None,
        persist_local: bool = False,
        max_local_bytes: int = _DEFAULT_MAX_LOCAL_BYTES,
    ) -> None:
        self._destination = destination
        self._environ = environ
        self._otel_export = otel_export
        self._langfuse_export = langfuse_export
        self._export_sink = export_sink
        self._persist_local = persist_local
        self._max_local_bytes = max(1, max_local_bytes)
        self._local: list[dict[str, Any]] = []
        self._network: list[str] = []

    def set_export_flags(self, *, otel_export: bool, langfuse_export: bool) -> None:
        self._otel_export = otel_export
        self._langfuse_export = langfuse_export

    def export_active(self) -> bool:
        return self._otel_export or self._langfuse_export or export_enabled(self._environ)

    def exported_to_network(self) -> bool:
        return bool(self._network)

    def network_calls(self) -> tuple[str, ...]:
        return tuple(self._network)

    def local_spans(self) -> list[dict[str, Any]]:
        return list(self._local)

    def _write_local(self, path: Path, record: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(record)) + "\n"
        if path.is_file() and path.stat().st_size + len(line.encode("utf-8")) > self._max_local_bytes:
            path.write_text(line, encoding="utf-8")
            return
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    @contextmanager
    def span(self, name: str, payload: Mapping[str, object] | None = None) -> Iterator[None]:
        cleaned = redact_mapping(payload or {})
        record: dict[str, Any] = {
            "name": redact_text(name),
            "payload": cleaned,
            "otel_export": self._otel_export or export_enabled(self._environ),
            "langfuse_export": self._langfuse_export,
        }
        self._local.append(record)
        if self._persist_local and self._destination is not None:
            self._write_local(self._destination, record)
        if self.export_active():
            sink = self._export_sink or self._destination
            if sink is not None:
                self._write_local(sink, record)
        yield
