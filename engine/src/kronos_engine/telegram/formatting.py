# SPDX-License-Identifier: AGPL-3.0-or-later
"""Redact secrets and format concise Telegram messages. No I/O."""

from __future__ import annotations

import re

_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_OPENSSH = re.compile(
    r"-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----",
    re.DOTALL,
)
_GITHUB_TOKEN = re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}\b")
_GITHUB_PAT = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")
_BOT_TOKEN = re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{30,}\b")
_BEARER = re.compile(r"(?i)\bbearer[=:\s]+[A-Za-z0-9._\-]+")
_AUTH_ENV = re.compile(r"(?i)\bKRONOS_AUTH_TOKEN=\S+")
_KEY_REF = re.compile(r"github:(?:controller|reviewer):private_key")
_INSTALL_BEARER = re.compile(r"\binstall-token\b")


def redact_secrets(text: str) -> str:
    cleaned = _PEM.sub("[redacted]", text)
    cleaned = _OPENSSH.sub("[redacted]", cleaned)
    cleaned = _GITHUB_TOKEN.sub("[redacted]", cleaned)
    cleaned = _GITHUB_PAT.sub("[redacted]", cleaned)
    cleaned = _BOT_TOKEN.sub("[redacted]", cleaned)
    cleaned = _BEARER.sub("bearer [redacted]", cleaned)
    cleaned = _AUTH_ENV.sub("KRONOS_AUTH_TOKEN=[redacted]", cleaned)
    cleaned = _KEY_REF.sub("[redacted]", cleaned)
    cleaned = _INSTALL_BEARER.sub("[redacted]", cleaned)
    return cleaned


def format_help() -> str:
    return (
        "Kronos Telegram commands:\n"
        "/help\n"
        "/goal repo:<id> | title | success criteria | non-goals | risk\n"
        "/status [goal_id]\n"
        "/pause <goal_id>\n"
        "/resume <goal_id>\n"
        "/approval <goal_id>\n"
        "Specify repo:<id> or set a default repository in Desktop Connections."
    )


def format_state_change(
    *,
    title: str,
    state: str,
    pr_url: str | None = None,
    extra: str | None = None,
) -> str:
    lines = [f"{title} is {state}."]
    if pr_url:
        lines.append(f"PR: {pr_url}")
    if extra:
        lines.append(extra)
    return redact_secrets("\n".join(lines))


def format_status_line(
    *,
    title: str,
    state: str,
    goal_id: str,
    reason: str | None = None,
    pr_url: str | None = None,
) -> str:
    parts = [f"{title} ({goal_id}) {state}"]
    if reason:
        parts.append(reason)
    if pr_url:
        parts.append(pr_url)
    return redact_secrets(" ".join(parts))
