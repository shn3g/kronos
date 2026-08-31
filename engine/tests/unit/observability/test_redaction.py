# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tokens, env values, customer data, and high-entropy secrets never persist."""

from __future__ import annotations

from kronos_engine.observability.redaction import redact_mapping, redact_text

PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEAfakeprivatekeymaterialforredactiontestxx\n"
    "-----END RSA PRIVATE KEY-----"
)
BOT_TOKEN = "123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
GITHUB_TOKEN = "ghp_" + ("A" * 36)
BEARER = "Bearer install-token"
HIGH_ENTROPY = "k8s_secret_" + ("Zx9q" * 8)


def test_redact_text_strips_tokens_pems_and_env_values() -> None:
    raw = (
        f"token={BOT_TOKEN} pem={PEM} github={GITHUB_TOKEN} {BEARER} "
        "KRONOS_AUTH_TOKEN=super-secret-value "
        "customer_email=ada@example.com "
        f"entropy={HIGH_ENTROPY}"
    )
    cleaned = redact_text(raw)
    assert BOT_TOKEN not in cleaned
    assert "PRIVATE KEY" not in cleaned
    assert GITHUB_TOKEN not in cleaned
    assert "install-token" not in cleaned
    assert "super-secret-value" not in cleaned
    assert "ada@example.com" not in cleaned
    assert HIGH_ENTROPY not in cleaned
    assert cleaned.count("[redacted]") >= 4


def test_redact_mapping_redacts_nested_secret_fields() -> None:
    payload = {
        "event": "external.wrote",
        "token": BOT_TOKEN,
        "headers": {"Authorization": BEARER, "X-Custom": "ok"},
        "env": {"KRONOS_AUTH_TOKEN": "leak-me", "PATH": "/usr/bin"},
        "pem": PEM,
        "customer": {"email": "ada@example.com", "repo": "acme/app"},
        "nested": [{"api_key": HIGH_ENTROPY, "sha": "abc123"}],
    }
    cleaned = redact_mapping(payload)
    encoded = str(cleaned)
    assert BOT_TOKEN not in encoded
    assert PEM not in encoded
    assert "leak-me" not in encoded
    assert "ada@example.com" not in encoded
    assert HIGH_ENTROPY not in encoded
    assert cleaned["headers"]["X-Custom"] == "ok"
    assert cleaned["env"]["PATH"] == "/usr/bin"
    assert cleaned["customer"]["repo"] == "acme/app"
    assert cleaned["nested"][0]["sha"] == "abc123"
