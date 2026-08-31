# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production poller records failures and does not die on SecretStoreError."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from tests.support.secrets import InMemorySecretStore
from tests.support.telegram_fixture import BOT_TOKEN

from kronos_engine.adapters.secrets.os_store import SecretStoreError
from kronos_engine.telegram.auth import BOT_TOKEN_REF
from kronos_engine.telegram.poller import TelegramPoller


class _BoomSecrets:
    def put(self, name: str, value: str) -> None:
        _ = name, value

    def get(self, name: str) -> str | None:
        _ = name
        raise SecretStoreError("OS credential storage could not read the secret")

    def delete(self, name: str) -> None:
        _ = name


class _BoomConnector:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def poll(self) -> int:
        raise self._error


def test_secret_store_error_records_failure_and_keeps_the_loop_alive() -> None:
    calls = {"n": 0}

    @contextmanager
    def factory() -> Iterator[_BoomConnector]:
        calls["n"] += 1
        yield _BoomConnector(RuntimeError("should not poll"))

    poller = TelegramPoller(_BoomSecrets(), factory)
    poller.tick()
    poller.tick()
    assert poller.failures == 2
    assert calls["n"] == 0


def test_transport_error_records_failure_and_redacts_bot_token_url() -> None:
    secrets = InMemorySecretStore()
    secrets.put(BOT_TOKEN_REF, BOT_TOKEN)
    logged: list[str] = []
    error = RuntimeError(
        f"Client error '502' for url 'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates'"
    )

    @contextmanager
    def factory() -> Iterator[_BoomConnector]:
        yield _BoomConnector(error)

    poller = TelegramPoller(secrets, factory, log=logged.append)
    poller.tick()
    poller.tick()
    assert poller.failures == 2
    assert poller.last_error is not None
    assert BOT_TOKEN not in poller.last_error
    assert "[redacted]" in poller.last_error
    combined = "\n".join(logged)
    assert BOT_TOKEN not in combined
    assert "[redacted]" in combined
