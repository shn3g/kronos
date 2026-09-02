# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unified diffs for chat file writes. No I/O."""

from __future__ import annotations

import difflib

MAX_PATCH_CHARS = 20_000


def unified_write_patch(*, path: str, before: str, after: str) -> str:
    from_file = "/dev/null" if before == "" else f"a/{path}"
    patch = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=from_file,
            tofile=f"b/{path}",
            n=3,
        )
    )
    if len(patch) <= MAX_PATCH_CHARS:
        return patch
    return f"{patch[:MAX_PATCH_CHARS]}\n... truncated ..."
