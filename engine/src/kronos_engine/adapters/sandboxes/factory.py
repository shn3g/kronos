# SPDX-License-Identifier: AGPL-3.0-or-later
"""Select the default in-process jail. Confined runtimes are opt-in and fail closed."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.adapters.sandboxes.local_unsafe import LocalUnsafeSandbox
from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.ports.sandbox import Sandbox


def default_sandbox(worktree: Path) -> ProcessJailSandbox:
    return ProcessJailSandbox(worktree)


def sandbox_for_policy(name: str, worktree: Path) -> Sandbox:
    normalized = name.strip().lower()
    if normalized in {"docker", "container", "swe-rex", "swerex"}:
        from kronos_engine.adapters.sandboxes.docker import DockerSandbox
        from kronos_engine.ports.sandbox import SandboxUnavailableError

        DockerSandbox(worktree)
        raise SandboxUnavailableError(
            "Docker/SWE-ReX is not selected until a confined runtime is available"
        )
    if normalized in {"unsafe", "local"}:
        return LocalUnsafeSandbox(worktree)
    return ProcessJailSandbox(worktree)
