# SPDX-License-Identifier: AGPL-3.0-or-later
"""Docker/SWE-ReX adapter. Not selected until a confined runtime is available."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.ports.sandbox import SandboxUnavailableError


class DockerSandbox:
    def __init__(self, worktree: Path) -> None:
        _ = worktree
        raise SandboxUnavailableError(
            "Docker/SWE-ReX is not selected until a confined runtime is available"
        )
