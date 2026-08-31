# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory Telegram Bot API. Tests never call api.telegram.org."""

from __future__ import annotations

from dataclasses import dataclass

BOT_TOKEN = "123456789:AATestTelegramBotTokenNotForProduction"
ALLOWED_USER = 4242
ALLOWED_CHAT = 9001
STRANGER_USER = 7777
STRANGER_CHAT = 8888


@dataclass(frozen=True, slots=True)
class FixtureUpdate:
    update_id: int
    user_id: int
    chat_id: int
    text: str


class TelegramFixture:
    """Fixture transport. The contract for CI; not the live Bot API."""

    def __init__(self) -> None:
        self.base_url = "fixture://telegram"
        self.queued: list[FixtureUpdate] = []
        self.sent: list[tuple[int, str]] = []
        self.get_calls = 0

    def queue_message(
        self,
        *,
        update_id: int,
        text: str,
        user_id: int = ALLOWED_USER,
        chat_id: int = ALLOWED_CHAT,
    ) -> None:
        self.queued.append(
            FixtureUpdate(update_id=update_id, user_id=user_id, chat_id=chat_id, text=text)
        )

    def get_updates(self, offset: int = 0, timeout: int = 0) -> list[FixtureUpdate]:
        _ = timeout
        self.get_calls += 1
        return [item for item in self.queued if item.update_id >= offset]

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    def texts_to(self, chat_id: int) -> list[str]:
        return [text for target, text in self.sent if target == chat_id]
