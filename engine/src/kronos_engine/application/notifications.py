# SPDX-License-Identifier: AGPL-3.0-or-later
"""Concise Telegram notifications. Secrets and raw logs never ship."""

from __future__ import annotations

from kronos_engine.state.telegram import SqliteTelegramStore
from kronos_engine.telegram.artifacts import supported_artifact
from kronos_engine.telegram.client import TelegramBotClient
from kronos_engine.telegram.formatting import format_state_change, redact_secrets


class NotificationService:
    def __init__(self, client: TelegramBotClient, store: SqliteTelegramStore) -> None:
        self._client = client
        self._store = store

    def notify_state_change(
        self,
        *,
        chat_id: int,
        title: str,
        state: str,
        pr_url: str | None = None,
        extra: str | None = None,
    ) -> None:
        self._client.send_message(
            chat_id,
            format_state_change(title=title, state=state, pr_url=pr_url, extra=extra),
        )

    def notify_failure(self, *, chat_id: int, reason: str, log_excerpt: str | None = None) -> None:
        _ = log_excerpt
        self._client.send_message(chat_id, redact_secrets(reason))

    def notify_artifact(self, *, chat_id: int, name: str, content: str) -> None:
        if not supported_artifact(name, content):
            self._client.send_message(chat_id, "unsupported artifact")
            return
        self._client.send_message(chat_id, redact_secrets(f"{name}\n{content}"))

    def notify_allowed_chats(
        self,
        *,
        title: str,
        state: str,
        pr_url: str | None = None,
        extra: str | None = None,
    ) -> None:
        for chat_id in self._store.load().allowed_chat_ids:
            self.notify_state_change(
                chat_id=chat_id,
                title=title,
                state=state,
                pr_url=pr_url,
                extra=extra,
            )

    def notify_failure_allowed(self, *, reason: str, log_excerpt: str | None = None) -> None:
        for chat_id in self._store.load().allowed_chat_ids:
            self.notify_failure(chat_id=chat_id, reason=reason, log_excerpt=log_excerpt)

    def notify_artifact_allowed(self, *, name: str, content: str) -> None:
        for chat_id in self._store.load().allowed_chat_ids:
            self.notify_artifact(chat_id=chat_id, name=name, content=content)
