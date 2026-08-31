# SPDX-License-Identifier: AGPL-3.0-or-later
"""Redact tokens, environment values, customer data, and high-entropy secrets."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[redacted]"

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
_BOT_URL = re.compile(r"/bot\d{8,}:[A-Za-z0-9_-]{30,}")
_BEARER = re.compile(r"(?i)\bbearer[=:\s]+[A-Za-z0-9._\-]+")
_AUTH_ENV = re.compile(r"(?i)\b(?:KRONOS_AUTH_TOKEN|GITHUB_TOKEN|GH_TOKEN)=\S+")
_KEY_REF = re.compile(r"github:(?:controller|reviewer):private_key")
_INSTALL_BEARER = re.compile(r"\binstall-token\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_ENV_ASSIGN = re.compile(
    r"(?i)\b([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY))=\S+"
)

_SECRET_KEYS = frozenset(
    {
        "token",
        "bot_token",
        "api_key",
        "apikey",
        "pem",
        "private_key",
        "privatekey",
        "password",
        "passwd",
        "authorization",
        "auth_token",
        "secret",
        "email",
        "customer_email",
    }
)
_SECRET_KEY_PARTS = re.compile(
    r"(token|secret|password|passwd|passphrase|api[_-]?key|private[_-]?key|credential|bearer|pem)",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    cleaned = _PEM.sub(REDACTED, text)
    cleaned = _OPENSSH.sub(REDACTED, cleaned)
    cleaned = _GITHUB_TOKEN.sub(REDACTED, cleaned)
    cleaned = _GITHUB_PAT.sub(REDACTED, cleaned)
    cleaned = _BOT_TOKEN.sub(REDACTED, cleaned)
    cleaned = _BOT_URL.sub("/bot[redacted]", cleaned)
    cleaned = _BEARER.sub("bearer [redacted]", cleaned)
    cleaned = _AUTH_ENV.sub(lambda match: match.group(0).split("=", 1)[0] + "=[redacted]", cleaned)
    cleaned = _ENV_ASSIGN.sub(lambda match: match.group(1) + "=[redacted]", cleaned)
    cleaned = _KEY_REF.sub(REDACTED, cleaned)
    cleaned = _INSTALL_BEARER.sub(REDACTED, cleaned)
    cleaned = _EMAIL.sub(REDACTED, cleaned)
    return _redact_high_entropy_tokens(cleaned)


def redact_mapping(payload: Mapping[str, object] | Sequence[object] | object) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _redact_value(str(key), value) for key, value in payload.items()}
    if isinstance(payload, tuple):
        return tuple(redact_mapping(item) for item in payload)
    if isinstance(payload, list):
        return [redact_mapping(item) for item in payload]
    if isinstance(payload, str):
        return redact_text(payload)
    return payload


def _redact_value(key: str, value: object) -> object:
    if _is_secret_key(key):
        if isinstance(value, Mapping | list | tuple):
            return redact_mapping(value)
        return REDACTED
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [
            redact_mapping(item) if not isinstance(item, str) else _redact_value(key, item)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            redact_mapping(item) if not isinstance(item, str) else _redact_value(key, item)
            for item in value
        )
    if isinstance(value, str):
        return redact_text(value)
    return value


def _is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    if lowered in _SECRET_KEYS:
        return True
    if lowered.startswith("kronos_auth") or lowered.endswith("_token"):
        return True
    return bool(_SECRET_KEY_PARTS.search(key))


def _redact_high_entropy_tokens(text: str) -> str:
    parts = re.split(r"(\s+)", text)

    def maybe(token: str) -> str:
        stripped = token.strip(".,;:\"'()[]{}")
        if _looks_high_entropy(stripped):
            return token.replace(stripped, REDACTED)
        return token

    return "".join(maybe(part) if not part.isspace() else part for part in parts)


def _looks_high_entropy(token: str) -> bool:
    if len(token) < 24:
        return False
    if token.startswith("http://") or token.startswith("https://"):
        return False
    if "/" in token or "\\" in token:
        return False
    if token.startswith("[") and token.endswith("]"):
        return False
    if len(token) >= 32 and all(ch in "0123456789abcdef" for ch in token):
        return True
    charset = set(token)
    if len(charset) < 8:
        return False
    counts: dict[str, int] = {}
    for ch in token:
        counts[ch] = counts.get(ch, 0) + 1
    entropy = -sum((n / len(token)) * math.log2(n / len(token)) for n in counts.values())
    return entropy >= 3.2
