# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from kronos_engine.application.chat import ChatTurn
from kronos_engine.application.chat_complete import chat_completion_messages


def test_chat_completion_messages_keep_system_user_and_assistant_roles() -> None:
    messages = chat_completion_messages(
        "You are Kronos.",
        (
            ChatTurn(role="user", content="What is broken?"),
            ChatTurn(role="assistant", content="I will look."),
            ChatTurn(role="tool", content="12 hits"),
            ChatTurn(role="assistant", content="Staff is missing."),
        ),
    )
    assert messages[0] == {"role": "system", "content": "You are Kronos."}
    assert messages[1] == {"role": "user", "content": "What is broken?"}
    assert messages[2] == {"role": "assistant", "content": "I will look."}
    assert messages[3]["role"] == "user"
    assert messages[3]["content"].startswith("[tool]")
    assert messages[4] == {"role": "assistant", "content": "Staff is missing."}
