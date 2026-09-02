# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from kronos_engine.application.chat_diff import unified_write_patch


def test_unified_write_patch_marks_replaced_lines() -> None:
    patch = unified_write_patch(path="hello.py", before="old\n", after="new\n")
    assert "a/hello.py" in patch
    assert "b/hello.py" in patch
    assert "-old" in patch
    assert "+new" in patch


def test_unified_write_patch_uses_dev_null_for_new_files() -> None:
    patch = unified_write_patch(path="fresh.py", before="", after="hi\n")
    assert "/dev/null" in patch
    assert "+hi" in patch


def test_unified_write_patch_truncates_huge_diffs() -> None:
    before = "x\n" * 8000
    after = "y\n" * 8000
    patch = unified_write_patch(path="big.py", before=before, after=after)
    assert patch.endswith("... truncated ...")
    assert len(patch) < 30_000
