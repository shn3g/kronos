# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jail worktree writes. Network off, non-root, secret-free, resource-limited."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from kronos_engine.domain.models import is_forbidden_secret_key
from kronos_engine.ports.sandbox import (
    PathEscapeError,
    SandboxCapabilities,
    SecretAccessError,
    UnsafeSandboxMergeRefused,
)

_DEFAULT_CAPS = SandboxCapabilities(
    network=False,
    secrets=False,
    root=False,
    unsafe=False,
    label="container: network-off, non-root, secret-free",
    memory_mb=512,
    cpu_limit=1.0,
    timeout_seconds=120.0,
    allows_autonomous_merge=False,
)


class ContainerSandbox:
    def __init__(self, worktree: Path) -> None:
        self._worktree = worktree
        self._worktree.mkdir(parents=True, exist_ok=True)

    def capabilities(self) -> SandboxCapabilities:
        return _DEFAULT_CAPS

    def resolve(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or candidate.anchor:
            raise PathEscapeError(f"absolute paths are forbidden: {relative}")
        if ".." in candidate.parts:
            raise PathEscapeError(f"path escape is forbidden: {relative}")
        root = self._worktree.resolve()
        target = (root / candidate).resolve()
        if root not in target.parents and target != root:
            raise PathEscapeError(f"path escape is forbidden: {relative}")
        return target

    def write_text(self, relative: str, content: str) -> Path:
        target = self.resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def worker_environment(self, extra: Mapping[str, str]) -> dict[str, str]:
        for key in extra:
            if is_forbidden_secret_key(key):
                raise SecretAccessError(f"worker env leak of secret or credential: {key}")
        return dict(extra)

    def authorize_autonomous_merge(self) -> None:
        raise UnsafeSandboxMergeRefused("default sandbox cannot authorize autonomous merge")
