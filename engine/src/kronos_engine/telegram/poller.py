# SPDX-License-Identifier: AGPL-3.0-or-later
"""Background Telegram poll loop. Failures are recorded; the thread stays alive."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from kronos_engine.adapters.secrets.os_store import SecretStoreError
from kronos_engine.ports.secrets import SecretStore
from kronos_engine.telegram.auth import BOT_TOKEN_REF
from kronos_engine.telegram.formatting import redact_secrets


class _Pollable(Protocol):
    def poll(self) -> int: ...


class TelegramPoller:
    def __init__(
        self,
        secrets: SecretStore,
        connector_factory: Callable[[], AbstractContextManager[_Pollable]],
        *,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.failures = 0
        self.last_error: str | None = None
        self._secrets = secrets
        self._connector_factory = connector_factory
        self._log = log

    def tick(self) -> None:
        try:
            token = self._secrets.get(BOT_TOKEN_REF)
        except SecretStoreError as error:
            self._record(error)
            return
        if not token:
            return
        try:
            with self._connector_factory() as connector:
                connector.poll()
        except Exception as error:
            self._record(error)

    def _record(self, error: BaseException) -> None:
        self.failures += 1
        self.last_error = redact_secrets(str(error))
        if self._log is not None:
            self._log(self.last_error)
