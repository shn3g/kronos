# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run configured test commands inside a claimed worktree."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


class ProcessGateRunner:
    def run(
        self, worktree: Path, commands: tuple[tuple[str, ...], ...]
    ) -> Sequence[Mapping[str, object]]:
        results: list[dict[str, object]] = []
        for argv in commands:
            if not argv:
                continue
            proc = subprocess.run(
                list(argv),
                cwd=worktree,
                capture_output=True,
                text=True,
                shell=False,
                check=False,
            )
            results.append(
                {
                    "name": argv[0],
                    "passed": proc.returncode == 0,
                    "output": (proc.stdout or "") + (proc.stderr or ""),
                }
            )
        return results
