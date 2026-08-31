# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured events and spans. Payloads are redacted before Recorder persistence."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from kronos_engine.application.recorder import Recorder
from kronos_engine.domain.events import StoredEvent
from kronos_engine.observability.otel import LocalMetrics, Tracer
from kronos_engine.observability.redaction import redact_mapping

POLICY = "policy.evaluated"
RETRIEVAL = "retrieval.searched"
MODEL = "model.called"
TOOL = "tool.called"
GIT = "git.wrote"
CI = "ci.checked"
REVIEW = "review.checked"
EXTERNAL_WRITE = "external.wrote"


class _Span:
    def __init__(
        self, emitter: StructuredEmitter, name: str, payload: Mapping[str, object]
    ) -> None:
        self._emitter = emitter
        self.name = name
        self._payload: dict[str, object] = dict(payload)

    def set(self, key: str, value: object) -> None:
        self._payload[key] = value


class StructuredEmitter:
    def __init__(
        self,
        recorder: Recorder,
        metrics: LocalMetrics | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._recorder = recorder
        self._metrics = metrics or LocalMetrics()
        self._tracer = tracer or Tracer()

    def emit(self, event_type: str, payload: Mapping[str, object]) -> StoredEvent:
        cleaned = redact_mapping(payload)
        stored, _row = self._recorder.emit(event_type, cleaned)
        self._metrics.inc(event_type)
        return stored

    @contextmanager
    def span(self, name: str, payload: Mapping[str, object] | None = None) -> Iterator[_Span]:
        span = _Span(self, name, payload or {})
        with self._tracer.span(name, dict(span._payload)):
            try:
                yield span
            finally:
                self.emit(name, span._payload)
