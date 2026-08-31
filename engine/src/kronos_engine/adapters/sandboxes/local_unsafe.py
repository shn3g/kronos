# SPDX-License-Identifier: AGPL-3.0-or-later
"""Visibly unsafe local unsandboxed execution. Cannot authorize autonomous merge."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.ports.sandbox import (
    SandboxCapabilities,
    UnsafeSandboxMergeRefused,
    refuse_unenforceable,
)

_UNSAFE = SandboxCapabilities(
    network=True,
    secrets=False,
    root=True,
    unsafe=True,
    label="UNSAFE: local unsandboxed execution",
    memory_mb=0,
    cpu_limit=0.0,
    timeout_seconds=0.0,
    allows_autonomous_merge=False,
)


class LocalUnsafeSandbox:
    def __init__(self, worktree: Path) -> None:
        self._inner = ProcessJailSandbox(worktree)

    def capabilities(self) -> SandboxCapabilities:
        return _UNSAFE

    def enforce_capabilities(self, *, network: bool, secrets: bool, root: bool) -> None:
        refuse_unenforceable(self.capabilities(), network=network, secrets=secrets, root=root)

    def resolve(self, relative: str) -> Path:
        return self._inner.resolve(relative)

    def write_text(self, relative: str, content: str) -> Path:
        return self._inner.write_text(relative, content)

    def worker_environment(self, extra: Mapping[str, str]) -> dict[str, str]:
        return self._inner.worker_environment(extra)

    def authorize_autonomous_merge(self) -> None:
        raise UnsafeSandboxMergeRefused(
            "UNSAFE local unsandboxed execution cannot be used for autonomous merges"
        )
