# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sandbox capability port. Default is an in-process path jail."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class PathEscapeError(ValueError):
    """Raised when a path would leave the worktree jail."""


class SecretAccessError(RuntimeError):
    """Raised when a worker environment leak of credentials is attempted."""


class UnsafeSandboxMergeRefused(RuntimeError):
    """Raised when an unsafe or default sandbox is asked to authorize merge."""


class CapabilityUnsupportedError(RuntimeError):
    """Raised when a request needs isolation the sandbox cannot apply."""


class SandboxUnavailableError(RuntimeError):
    """Raised when a confined runtime adapter is requested but not selected."""


@dataclass(frozen=True, slots=True)
class SandboxCapabilities:
    network: bool
    secrets: bool
    root: bool
    unsafe: bool
    label: str
    memory_mb: int
    cpu_limit: float
    timeout_seconds: float
    allows_autonomous_merge: bool


def refuse_unenforceable(
    caps: SandboxCapabilities, *, network: bool, secrets: bool, root: bool
) -> None:
    if network is False and caps.network is True:
        raise CapabilityUnsupportedError("sandbox cannot drop network")
    if root is False and caps.root is True:
        raise CapabilityUnsupportedError("sandbox cannot drop root")
    if secrets is False and caps.secrets is True:
        raise CapabilityUnsupportedError("sandbox cannot run secret-free")


class Sandbox(Protocol):
    def capabilities(self) -> SandboxCapabilities: ...

    def enforce_capabilities(self, *, network: bool, secrets: bool, root: bool) -> None: ...

    def resolve(self, relative: str) -> Path: ...

    def write_text(self, relative: str, content: str) -> Path: ...

    def worker_environment(self, extra: Mapping[str, str]) -> dict[str, str]: ...

    def authorize_autonomous_merge(self) -> None: ...
