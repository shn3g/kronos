# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import Iterator
from threading import Event

import pytest

from kronos_engine.adapters.models.openai_compatible import (
    CompletionCancelled,
    OpenAICompatibleProvider,
    delta_text_from_sse_payload,
)
from kronos_engine.domain.models import ModelProfile, ResourceLimits
from kronos_engine.ports.model_provider import CompletionRequest


class _SseTransport:
    def __init__(self, payloads: list[str], *, raise_cancel_after: int | None = None) -> None:
        self.payloads = payloads
        self.raise_cancel_after = raise_cancel_after
        self.posts: list[dict[str, object]] = []
        self.closed = False

    def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]:
        _ = url, timeout
        return 200, {"data": []}

    def post(
        self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, object]]:
        _ = url, json, headers, timeout
        raise AssertionError("non-stream post should not run for complete_stream")

    def post_sse(
        self,
        url: str,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float,
        cancel: Event,
    ) -> Iterator[str]:
        _ = url, headers, timeout, cancel
        self.posts.append(json)
        for index, payload in enumerate(self.payloads):
            if self.raise_cancel_after is not None and index >= self.raise_cancel_after:
                self.closed = True
                raise CompletionCancelled(
                    "".join(
                        delta_text_from_sse_payload(item)
                        for item in self.payloads[: self.raise_cancel_after]
                    )
                )
            yield payload


def _profile() -> ModelProfile:
    return ModelProfile(
        id="prof_planner",
        display_name="Local planner",
        role="planner",
        provider_id="prov_ollama",
        model_id="llama3",
        billed=False,
        approved_fallbacks=(),
        limits=ResourceLimits(
            max_tokens=128,
            max_attempts=3,
            timeout_seconds=15.0,
            cost_ceiling=0.0,
        ),
    )


def test_sse_payload_extracts_delta_content() -> None:
    assert delta_text_from_sse_payload('{"choices":[{"delta":{"content":"Hello"}}]}') == "Hello"
    assert delta_text_from_sse_payload("[DONE]") == ""


def test_sse_payload_prefers_content_over_reasoning_fields() -> None:
    payload = (
        '{"choices":[{"delta":{"content":"answer","reasoning_content":"think","reasoning":"also"}}]}'
    )
    assert delta_text_from_sse_payload(payload) == "answer"


def test_sse_payload_falls_back_to_reasoning_content() -> None:
    payload = '{"choices":[{"delta":{"reasoning_content":"thinking"}}]}'
    assert delta_text_from_sse_payload(payload) == "thinking"


def test_sse_payload_falls_back_to_reasoning() -> None:
    payload = '{"choices":[{"delta":{"reasoning":"chain"}}]}'
    assert delta_text_from_sse_payload(payload) == "chain"


def test_sse_payload_ignores_empty_content_for_reasoning_fallback() -> None:
    payload = '{"choices":[{"delta":{"content":"","reasoning_content":"thinking"}}]}'
    assert delta_text_from_sse_payload(payload) == "thinking"


def test_prepare_omits_max_tokens_when_zero() -> None:
    transport = _SseTransport(['{"choices":[{"delta":{"content":"ok"}}]}', "[DONE]"])
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        transport=transport,
    )
    profile = _profile()
    profile = ModelProfile(
        id=profile.id,
        display_name=profile.display_name,
        role=profile.role,
        provider_id=profile.provider_id,
        model_id=profile.model_id,
        billed=profile.billed,
        approved_fallbacks=profile.approved_fallbacks,
        limits=ResourceLimits(
            max_tokens=0,
            max_attempts=3,
            timeout_seconds=15.0,
            cost_ceiling=0.0,
        ),
    )
    list(
        provider.complete_stream(
            CompletionRequest(profile=profile, prompt="hi"),
            secret=None,
            cancel=Event(),
        )
    )
    assert "max_tokens" not in transport.posts[0]


def test_complete_stream_yields_deltas_and_sets_stream_flag() -> None:
    transport = _SseTransport(
        [
            '{"choices":[{"delta":{"content":"Hello"}}]}',
            '{"choices":[{"delta":{"content":" world"}}]}',
            "[DONE]",
        ]
    )
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        transport=transport,
    )
    chunks = list(
        provider.complete_stream(
            CompletionRequest(profile=_profile(), prompt="hi"),
            secret=None,
            cancel=Event(),
        )
    )
    assert chunks == ["Hello", " world"]
    assert transport.posts[0]["stream"] is True


def test_complete_stream_sends_chat_roles_when_messages_are_provided() -> None:
    transport = _SseTransport(
        [
            '{"choices":[{"delta":{"content":"ok"}}]}',
            "[DONE]",
        ]
    )
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        transport=transport,
    )
    list(
        provider.complete_stream(
            CompletionRequest(
                profile=_profile(),
                prompt="flattened",
                messages=(
                    {"role": "system", "content": "You are Kronos."},
                    {"role": "user", "content": "Hi"},
                ),
            ),
            secret=None,
            cancel=Event(),
        )
    )
    assert transport.posts[0]["messages"] == [
        {"role": "system", "content": "You are Kronos."},
        {"role": "user", "content": "Hi"},
    ]


def test_complete_stream_preserves_multimodal_content_parts() -> None:
    transport = _SseTransport(['{"choices":[{"delta":{"content":"ok"}}]}', "[DONE]"])
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        transport=transport,
    )
    parts: list[dict[str, object]] = [
        {"type": "text", "text": "What is in this image?"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
        },
    ]

    list(
        provider.complete_stream(
            CompletionRequest(
                profile=_profile(),
                prompt="flattened",
                messages=({"role": "user", "content": parts},),
            ),
            secret=None,
            cancel=Event(),
        )
    )

    assert transport.posts[0]["messages"] == [{"role": "user", "content": parts}]


def test_complete_stream_closes_when_cancelled() -> None:
    transport = _SseTransport(
        [
            '{"choices":[{"delta":{"content":"Hi"}}]}',
            '{"choices":[{"delta":{"content":" there"}}]}',
        ],
        raise_cancel_after=1,
    )
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        billed=False,
        transport=transport,
    )
    chunks: list[str] = []
    with pytest.raises(CompletionCancelled) as error:
        for chunk in provider.complete_stream(
            CompletionRequest(profile=_profile(), prompt="hi"),
            secret=None,
            cancel=Event(),
        ):
            chunks.append(chunk)
    assert chunks == ["Hi"]
    assert error.value.partial == "Hi"
    assert transport.closed is True
