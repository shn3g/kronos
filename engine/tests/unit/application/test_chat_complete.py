# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from kronos_engine.application.chat import ChatTurn
from kronos_engine.application.chat_complete import chat_completion_messages
from kronos_engine.application.chat_images import ChatImagePart


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


def test_chat_completion_messages_use_vision_parts_for_pasted_images() -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
    )
    messages = chat_completion_messages(
        "You are Kronos.",
        (
            ChatTurn(
                role="user",
                content="What is this screen?",
                images=(ChatImagePart(mime="image/png", data=png),),
            ),
        ),
    )
    content = messages[1]["content"]
    assert messages[1]["role"] == "user"
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "What is this screen?"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
