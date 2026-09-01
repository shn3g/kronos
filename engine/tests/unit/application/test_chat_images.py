# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64

import pytest

from kronos_engine.application.chat_images import (
    MAX_CHAT_IMAGE_BYTES,
    ChatImagePart,
    append_image_markers,
    decode_chat_image,
    decode_chat_images,
    load_chat_image,
    save_chat_image,
    split_user_text_and_image_ids,
    user_message_content_parts,
)

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
TINY_PNG = base64.b64decode(TINY_PNG_B64)


def test_decode_chat_image_accepts_a_small_png() -> None:
    decoded = decode_chat_image(mime="image/png", data_base64=TINY_PNG_B64)

    assert decoded.mime == "image/png"
    assert decoded.data == TINY_PNG


def test_decode_chat_image_rejects_plain_text_and_oversize_and_bad_ids(
    tmp_path,
) -> None:
    with pytest.raises(ValueError, match="png, jpeg, webp, or gif"):
        decode_chat_image(mime="text/plain", data_base64=TINY_PNG_B64)

    padded = b"\x89PNG\r\n\x1a\n" + b"x" * (MAX_CHAT_IMAGE_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        decode_chat_image(mime="image/png", data_base64=base64.b64encode(padded).decode("ascii"))

    with pytest.raises(ValueError, match="invalid"):
        decode_chat_image(mime="image/png", data_base64="%%%not-base64%%%")

    with pytest.raises(ValueError, match="up to 3"):
        decode_chat_images(
            [
                {"mime": "image/png", "data": TINY_PNG_B64},
                {"mime": "image/png", "data": TINY_PNG_B64},
                {"mime": "image/png", "data": TINY_PNG_B64},
                {"mime": "image/png", "data": TINY_PNG_B64},
            ]
        )

    root = tmp_path / "chat-images"
    with pytest.raises(LookupError):
        load_chat_image(root, "chat_1", "../secret")
    with pytest.raises(LookupError):
        load_chat_image(root, "../chat_1", "img_abc")


def test_save_and_load_round_trip_stays_inside_the_session_folder(tmp_path) -> None:
    root = tmp_path / "chat-images"
    decoded = decode_chat_image(mime="image/png", data_base64=TINY_PNG_B64)

    image_id = save_chat_image(root, "chat_alpha", decoded)
    loaded = load_chat_image(root, "chat_alpha", image_id)

    assert image_id.startswith("img_")
    assert loaded.mime == "image/png"
    assert loaded.data == TINY_PNG
    stored = next((root / "chat_alpha").iterdir())
    assert stored.name.startswith(image_id)
    with pytest.raises(LookupError):
        load_chat_image(root, "chat_other", image_id)


def test_markers_round_trip_and_vision_parts_use_a_data_url() -> None:
    marked = append_image_markers("What is this?", ["img_aaa", "img_bbb"])
    text, ids = split_user_text_and_image_ids(marked)

    assert text == "What is this?"
    assert ids == ("img_aaa", "img_bbb")
    assert "kronos-image:img_aaa" in marked

    parts = user_message_content_parts(
        "What is this?",
        (ChatImagePart(mime="image/png", data=TINY_PNG),),
    )
    assert parts[0] == {"type": "text", "text": "What is this?"}
    assert parts[1]["type"] == "image_url"
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert url.endswith(TINY_PNG_B64) or TINY_PNG_B64 in url
