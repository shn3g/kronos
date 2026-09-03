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


def test_tracer_writes_redacted_sink_from_ops_settings_not_env(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("KRONOS_OTEL_EXPORT", raising=False)
    sink = tmp_path / "otel-export.jsonl"
    tracer = Tracer(
        destination=tmp_path / "spans.jsonl",
        environ={},
        otel_export=True,
        langfuse_export=True,
        export_sink=sink,
    )
    with tracer.span("model.called", {"prompt": BOT, "repository_id": "repo_alpha"}):
        pass
    assert tracer.exported_to_network() is False
    assert tracer.network_calls() == ()
    assert sink.is_file()
    text = sink.read_text(encoding="utf-8")
    assert "model.called" in text
    assert BOT not in text
    assert "repo_alpha" in text
    assert "langfuse" in text or "otel" in text


def test_tracer_appends_local_spans_without_rewriting_the_whole_file(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    tracer = Tracer(destination=path, persist_local=True)
    with tracer.span("first", {}):
        pass
    first = path.read_text(encoding="utf-8")
    with tracer.span("second", {}):
        pass
    second = path.read_text(encoding="utf-8")
    assert second.startswith(first)
    assert second.count("\n") == 2
    assert "first" in second and "second" in second


def test_tracer_caps_local_span_file_size(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    tracer = Tracer(destination=path, persist_local=True, max_local_bytes=400)
    for index in range(40):
        with tracer.span(f"span-{index}", {"n": index}):
            pass
    assert path.stat().st_size <= 400 + 200
    text = path.read_text(encoding="utf-8")
    assert "span-" in text


def test_tracer_skips_disk_when_persist_local_is_false(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    tracer = Tracer(destination=path, persist_local=False)
    with tracer.span("http.request", {"method": "GET"}):
        pass
    assert not path.exists()
    assert tracer.local_spans()


def test_configure_logging_uses_rotating_file_handler(tmp_path: Path) -> None:
    import logging
    from logging.handlers import RotatingFileHandler

    log_dir = tmp_path / "logs"
    configure_logging(log_dir, max_bytes=1024, backup_count=2)
    logger = logging.getLogger("kronos")
    handlers = [handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)]
    assert handlers
    assert handlers[0].maxBytes == 1024
    assert handlers[0].backupCount == 2
