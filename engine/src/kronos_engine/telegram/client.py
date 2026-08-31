# SPDX-License-Identifier: AGPL-3.0-or-later
"""Telegram Bot API client. Fixture transport is the CI contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from kronos_engine.ports.secrets import SecretStore
from kronos_engine.telegram.auth import BOT_TOKEN_REF
from kronos_engine.telegram.formatting import redact_secrets


@dataclass(frozen=True, slots=True)
class TelegramUpdate:
    update_id: int
    user_id: int
    chat_id: int
    text: str


class TelegramTransport(Protocol):
    def get_updates(self, offset: int, timeout: int = 0) -> Sequence[object]: ...

    def send_message(self, chat_id: int, text: str) -> None: ...


class TelegramBotClient:
    def __init__(self, secrets: SecretStore, transport: TelegramTransport) -> None:
        self._secrets = secrets
        self._transport = transport

    def token_present(self) -> bool:
        token = self._secrets.get(BOT_TOKEN_REF)
        return bool(token)

    def get_updates(self, offset: int) -> list[TelegramUpdate]:
        if not self.token_present():
            return []
        raw = self._transport.get_updates(offset, 0)
        updates: list[TelegramUpdate] = []
        for item in raw:
            updates.append(
                TelegramUpdate(
                    update_id=int(getattr(item, "update_id")),
                    user_id=int(getattr(item, "user_id")),
                    chat_id=int(getattr(item, "chat_id")),
                    text=str(getattr(item, "text")),
                )
            )
        return updates

    def send_message(self, chat_id: int, text: str) -> None:
        self._transport.send_message(chat_id, redact_secrets(text)[:4000])


class HttpxTelegramTransport:
    """Live Bot API transport. Tests inject TelegramFixture instead."""

    def __init__(self, token: str, *, base_url: str = "https://api.telegram.org") -> None:
        self._token = token
        self.base_url = base_url.rstrip("/")

    def get_updates(self, offset: int, timeout: int = 0) -> list[TelegramUpdate]:
        payload = self._request(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
        )
        raw_result = payload.get("result", [])
        if not isinstance(raw_result, list):
            return []
        updates: list[TelegramUpdate] = []
        for item in raw_result:
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            if not isinstance(message, dict):
                continue
            chat_raw = message.get("chat")
            user_raw = message.get("from")
            chat = chat_raw if isinstance(chat_raw, dict) else {}
            user = user_raw if isinstance(user_raw, dict) else {}
            text = message.get("text")
            if not isinstance(text, str):
                continue
            updates.append(
                TelegramUpdate(
                    update_id=int(item.get("update_id") or 0),
                    user_id=int(user.get("id") or 0),
                    chat_id=int(chat.get("id") or 0),
                    text=text,
                )
            )
        return updates

    def send_message(self, chat_id: int, text: str) -> None:
        self._request("sendMessage", {"chat_id": chat_id, "text": text})

    def _request(self, method: str, body: dict[str, object]) -> dict[str, object]:
        import httpx

        url = f"{self.base_url}/bot{self._token}/{method}"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=body)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return {}
            return payload
