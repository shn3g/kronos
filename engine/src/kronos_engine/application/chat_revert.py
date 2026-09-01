# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fold chat write events into the Changes list. No I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def fold_workspace_diffs(
    events: Sequence[tuple[str, Mapping[str, object]]],
) -> list[dict[str, object]]:
    folded: dict[tuple[str, str], dict[str, object]] = {}
    order: list[tuple[str, str]] = []
    for kind, payload in events:
        repo_id = str(payload.get("repository_id") or "")
        path = str(payload.get("path") or payload.get("url") or kind)
        key = (repo_id, path)
        if kind == "git.reverted":
            folded.pop(key, None)
            order = [item for item in order if item != key]
            continue
        if kind not in {"git.wrote", "external.wrote"}:
            continue
        if key not in folded:
            order.append(key)
        folded[key] = {
            "path": path,
            "summary": str(payload.get("summary") or kind),
            "repository_id": repo_id,
            "patch": str(payload.get("patch") or ""),
        }
    return [folded[key] for key in order if key in folded]
