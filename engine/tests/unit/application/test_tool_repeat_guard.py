# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for repeated chat tool-call detection."""

from __future__ import annotations

from kronos_engine.application.chat_tools import ToolCall
from kronos_engine.application.tool_repeat_guard import ToolCallRepeatGuard


def test_blocks_an_exact_repeat_after_a_remembered_success() -> None:
    guard = ToolCallRepeatGuard(window_size=3)
    call = ToolCall(name="list_files", arguments={"glob": "src/**/*.py"})

    assert guard.allow(call)
    guard.remember_success(call)
    assert not guard.allow(call)


def test_allows_retry_when_prior_attempt_was_not_remembered() -> None:
    guard = ToolCallRepeatGuard(window_size=3)
    call = ToolCall(name="list_files", arguments={"glob": "src/**/*.py"})

    assert guard.allow(call)
    # Failed attempts must not call remember_success — retry stays allowed.
    assert guard.allow(call)


def test_treats_equivalent_argument_order_as_an_exact_repeat() -> None:
    guard = ToolCallRepeatGuard(window_size=3)
    first = ToolCall(name="write_file", arguments={"path": "a.py", "content": "x"})
    again = ToolCall(name="write_file", arguments={"content": "x", "path": "a.py"})

    assert guard.allow(first)
    guard.remember_success(first)
    assert not guard.allow(again)


def test_permits_a_call_again_after_it_leaves_the_recent_window() -> None:
    guard = ToolCallRepeatGuard(window_size=2)
    first = ToolCall(name="list_files", arguments={"glob": "src/**/*.py"})

    assert guard.allow(first)
    guard.remember_success(first)
    assert guard.allow(ToolCall(name="read_file", arguments={"path": "a.py"}))
    guard.remember_success(ToolCall(name="read_file", arguments={"path": "a.py"}))
    assert guard.allow(ToolCall(name="search_memory", arguments={"query": "a"}))
    guard.remember_success(ToolCall(name="search_memory", arguments={"query": "a"}))
    assert guard.allow(first)
