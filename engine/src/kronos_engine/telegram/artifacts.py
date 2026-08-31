# SPDX-License-Identifier: AGPL-3.0-or-later
"""Supported Telegram artifacts. Secrets and uncontrolled logs are refused."""

from __future__ import annotations

from kronos_engine.telegram.formatting import redact_secrets

_ALLOWED_SUFFIXES = (".txt", ".md")
_FORBIDDEN_NAMES = {"id_rsa", "engine.log"}
_FORBIDDEN_SUFFIXES = (".pem", ".key")


def supported_artifact(name: str, content: str) -> bool:
    lowered = name.lower().rsplit("/", 1)[-1]
    if lowered in _FORBIDDEN_NAMES:
        return False
    if lowered.endswith(_FORBIDDEN_SUFFIXES):
        return False
    if "PRIVATE KEY" in content:
        return False
    if "KRONOS_AUTH_TOKEN" in content:
        return False
    if redact_secrets(content) != content:
        return False
    return lowered.endswith(_ALLOWED_SUFFIXES)
