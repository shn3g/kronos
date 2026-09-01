# SPDX-License-Identifier: AGPL-3.0-or-later
"""Executor profile selection: standard aliases controlled; CLI falls back when missing."""

from __future__ import annotations

import pytest

from kronos_engine.adapters.executors.controlled import ControlledOpenExecutor
from kronos_engine.adapters.executors.cursor import CursorExecutor
from kronos_engine.adapters.executors.opencode import OpencodeExecutor
from kronos_engine.application.composition import select_executor


def test_standard_profile_is_controlled() -> None:
    executor = select_executor("standard")
    assert isinstance(executor, ControlledOpenExecutor)


def test_controlled_profile_is_controlled() -> None:
    executor = select_executor("controlled")
    assert isinstance(executor, ControlledOpenExecutor)


def test_cursor_profile_uses_cursor_when_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_cursor_cli",
        lambda: object(),
    )
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_opencode_cli",
        lambda: None,
    )
    executor = select_executor("cursor")
    assert isinstance(executor, CursorExecutor)


def test_cursor_profile_falls_back_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_cursor_cli",
        lambda: None,
    )
    executor = select_executor("cursor")
    assert isinstance(executor, ControlledOpenExecutor)


def test_opencode_profile_uses_opencode_when_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_cursor_cli",
        lambda: None,
    )
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_opencode_cli",
        lambda: object(),
    )
    executor = select_executor("opencode")
    assert isinstance(executor, OpencodeExecutor)


def test_opencode_profile_falls_back_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kronos_engine.application.composition.detect_opencode_cli",
        lambda: None,
    )
    executor = select_executor("opencode")
    assert isinstance(executor, ControlledOpenExecutor)
