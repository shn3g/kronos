# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validate, store, and format pasted chat images. Disk I/O stays at the edges."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

ALLOWED_CHAT_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
MAX_CHAT_IMAGE_BYTES = 2 * 1024 * 1024
MAX_CHAT_IMAGES_PER_TURN = 3
_MARKER_RE = re.compile(r"!\[Pasted image\]\(kronos-image:([A-Za-z0-9_-]+)\)")
_EXT_FOR_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
_MIME_FOR_EXT = {ext: mime for mime, ext in _EXT_FOR_MIME.items()}


@dataclass(frozen=True, slots=True)
class ChatImageInput:
    mime: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ChatImagePart:
    mime: str
    data: bytes


def decode_chat_image(*, mime: str, data_base64: str) -> ChatImageInput:
    kind = mime.strip().lower()
    if kind == "image/jpg":
        kind = "image/jpeg"
    if kind not in ALLOWED_CHAT_IMAGE_TYPES:
        raise ValueError("Kronos can only use png, jpeg, webp, or gif images.")
    compact = "".join(data_base64.split())
    if compact == "":
        raise ValueError("image data is invalid")
    try:
        data = base64.b64decode(compact, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("image data is invalid") from error
    if data == b"":
        raise ValueError("image data is invalid")
    if len(data) > MAX_CHAT_IMAGE_BYTES:
        raise ValueError("That image is too large. Use a file under 2 MB.")
    if not _bytes_match_mime(kind, data):
        raise ValueError("image data is invalid")
    return ChatImageInput(mime=kind, data=data)


def decode_chat_images(items: Sequence[Mapping[str, str]]) -> tuple[ChatImageInput, ...]:
    if len(items) > MAX_CHAT_IMAGES_PER_TURN:
        raise ValueError("You can paste up to 3 images in one message.")
    return tuple(
        decode_chat_image(mime=item.get("mime", ""), data_base64=item.get("data", ""))
        for item in items
    )


def chat_path_id_ok(value: str) -> bool:
    if value == "" or "/" in value or "\\" in value or ".." in value:
        return False
    return all(ch.isalnum() or ch in "_-" for ch in value)


def image_marker(image_id: str) -> str:
    return f"![Pasted image](kronos-image:{image_id})"


def append_image_markers(text: str, image_ids: Sequence[str]) -> str:
    markers = "\n".join(image_marker(item) for item in image_ids)
    compact = text.strip()
    if compact == "":
        return markers
    if markers == "":
        return compact
    return f"{compact}\n{markers}"


def split_user_text_and_image_ids(content: str) -> tuple[str, tuple[str, ...]]:
    ids = tuple(_MARKER_RE.findall(content))
    text = _MARKER_RE.sub("", content).strip()
    return text, ids


def user_message_content_parts(
    text: str, images: Sequence[ChatImagePart]
) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = []
    if text.strip() != "":
        parts.append({"type": "text", "text": text})
    for image in images:
        encoded = base64.b64encode(image.data).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.mime};base64,{encoded}"},
            }
        )
    return parts


def save_chat_image(root: Path, session_id: str, image: ChatImageInput) -> str:
    if not chat_path_id_ok(session_id):
        raise ValueError("session is invalid")
    image_id = f"img_{uuid4().hex[:16]}"
    folder = root / session_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{image_id}.{_EXT_FOR_MIME[image.mime]}"
    if not _is_inside(root.resolve(), path.resolve()):
        raise ValueError("session is invalid")
    path.write_bytes(image.data)
    return image_id


def load_chat_image(root: Path, session_id: str, image_id: str) -> ChatImageInput:
    if not chat_path_id_ok(session_id) or not chat_path_id_ok(image_id):
        raise LookupError("chat image not found")
    folder = root / session_id
    for ext, mime in _MIME_FOR_EXT.items():
        path = folder / f"{image_id}.{ext}"
        if not path.is_file():
            continue
        if not _is_inside(root.resolve(), path.resolve()):
            raise LookupError("chat image not found")
        return ChatImageInput(mime=mime, data=path.read_bytes())
    raise LookupError("chat image not found")


def _bytes_match_mime(mime: str, data: bytes) -> bool:
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime == "image/gif":
        return data.startswith(b"GIF87a") or data.startswith(b"GIF89a")
    if mime == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _is_inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True
