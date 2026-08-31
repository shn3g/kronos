# SPDX-License-Identifier: AGPL-3.0-or-later
"""Allowlists, update dedup, and command/approval rate limits."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from kronos_engine.state.telegram import SqliteTelegramStore

BOT_TOKEN_REF = "telegram:bot_token"
COMMAND_LIMIT = 10
APPROVAL_LIMIT = 3
RATE_WINDOW_SECONDS = 60.0
BOTFATHER_URL = "https://t.me/BotFather"
BOTFATHER_STEPS = (
    "Open BotFather in Telegram and create a bot with /newbot.",
    "Save the bot token in a local file. Do not paste it into the desktop WebView.",
    "Import that file from Connections. Kronos stores the token in OS credential storage.",
    "Add allowed Telegram user IDs and chat IDs. Empty allowlists fail closed.",
)


class UnauthorizedTelegram(PermissionError):
    """Raised when the user or chat is not explicitly allowed."""


class TelegramRateLimited(PermissionError):
    """Raised when command or approval volume exceeds the window."""


class AmbiguousRepository(ValueError):
    """Raised when a command does not name a safe repository."""


class TelegramAuthorizer:
    def __init__(
        self,
        store: SqliteTelegramStore,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or time.monotonic

    def require_allowed(self, user_id: int, chat_id: int) -> None:
        settings = self._store.load()
        if not settings.allowed_user_ids or not settings.allowed_chat_ids:
            raise UnauthorizedTelegram("telegram allowlist is empty")
        if user_id not in settings.allowed_user_ids:
            raise UnauthorizedTelegram("telegram user is not allowed")
        if chat_id not in settings.allowed_chat_ids:
            raise UnauthorizedTelegram("telegram chat is not allowed")

    def consume(self, user_id: int, *, approval: bool = False) -> None:
        allowed = self._store.allow_request(
            user_id,
            self._clock(),
            approval=approval,
            command_limit=COMMAND_LIMIT,
            approval_limit=APPROVAL_LIMIT,
            window_seconds=RATE_WINDOW_SECONDS,
        )
        if not allowed:
            raise TelegramRateLimited("rate limit")

    def resolve_repository(
        self,
        explicit_id: str | None,
        enrolled_ids: Sequence[str],
    ) -> str:
        known = set(enrolled_ids)
        if explicit_id:
            if explicit_id not in known:
                raise AmbiguousRepository("repository is not enrolled")
            return explicit_id
        default = self._store.load().default_repository_id
        if default and default in known:
            return default
        raise AmbiguousRepository("repository is required")
