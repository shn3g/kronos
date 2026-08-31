# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local logs redact secrets. OTEL export is off by default and never networks in CI."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.observability.logging import configure_logging, get_logger
from kronos_engine.observability.otel import LocalMetrics, Tracer, export_enabled

BOT = "123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def test_structured_logs_redact_tokens_before_disk(tmp_path: Path, monkeypatch: object) -> None:
    log_dir = tmp_path / "logs"
    configure_logging(log_dir)
    get_logger("kronos.test").warning("bot=%s path=%s", BOT, "/usr/bin")
    files = list(log_dir.glob("*.log"))
    assert files
    text = files[0].read_text(encoding="utf-8")
    assert BOT not in text
    assert "[redacted]" in text
    assert "/usr/bin" in text


def test_otel_export_is_off_by_default_and_ignores_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("KRONOS_OTEL_EXPORT", raising=False)
    monkeypatch.setenv("KRONOS_OTEL_ENDPOINT", "https://example.invalid/v1/traces")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    assert export_enabled() is False
    tracer = Tracer(destination=tmp_path / "spans.json")
    with tracer.span("model.called", {"prompt": BOT}):
        pass
    assert tracer.exported_to_network() is False
    assert tracer.network_calls() == ()
    local = tracer.local_spans()
    assert local
    assert BOT not in str(local)


def test_local_metrics_count_events_without_export(monkeypatch) -> None:
    monkeypatch.delenv("KRONOS_OTEL_EXPORT", raising=False)
    metrics = LocalMetrics()
    metrics.inc("model.called")
    metrics.inc("model.called")
    metrics.inc("git.wrote")
    snap = metrics.snapshot()
    assert snap["model.called"] == 2
    assert snap["git.wrote"] == 1
    assert export_enabled() is False
