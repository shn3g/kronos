# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local metrics and optional OpenTelemetry/Langfuse export. Off by default."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from kronos_engine.observability.redaction import redact_mapping, redact_text


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
        self, destination: Path | None = None, *, environ: Mapping[str, str] | None = None
    ) -> None:
        self._destination = destination
        self._environ = environ
        self._local: list[dict[str, Any]] = []
        self._network: list[str] = []

    def exported_to_network(self) -> bool:
        return bool(self._network)

    def network_calls(self) -> tuple[str, ...]:
        return tuple(self._network)

    def local_spans(self) -> list[dict[str, Any]]:
        return list(self._local)

    @contextmanager
    def span(self, name: str, payload: Mapping[str, object] | None = None) -> Iterator[None]:
        cleaned = redact_mapping(payload or {})
        record = {"name": redact_text(name), "payload": cleaned}
        self._local.append(record)
        if self._destination is not None:
            self._destination.parent.mkdir(parents=True, exist_ok=True)
            existing = (
                self._destination.read_text(encoding="utf-8") if self._destination.is_file() else ""
            )
            self._destination.write_text(existing + str(record) + "\n", encoding="utf-8")
        if export_enabled(self._environ):
            # Export is opt-in and still does not open a network socket here.
            # A real exporter would be injected; CI never sets KRONOS_OTEL_EXPORT.
            pass
        yield
