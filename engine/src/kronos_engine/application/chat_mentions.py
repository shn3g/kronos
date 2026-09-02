# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse @path tokens from chat drafts. No I/O."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

_MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9_./\\-]+)")
MAX_MENTIONED_PATHS = 6


def mentioned_workspace_paths(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    paths: list[str] = []
    for match in _MENTION.finditer(text):
        normalized = match.group(1).rstrip(".,;:)").replace("\\", "/")
        if not _is_safe_relpath(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        paths.append(normalized)
        if len(paths) >= MAX_MENTIONED_PATHS:
            break
    return tuple(paths)


def _is_safe_relpath(path: str) -> bool:
    if path == "" or path.startswith("/"):
        return False
    relative = PurePosixPath(path)
    if relative.is_absolute():
        return False
    return not any(part in {"", ".", "..", ".git"} for part in relative.parts)
