# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI-compatible embeddings contract: fake HTTP only, dense degrades on failure."""

from __future__ import annotations

from kronos_engine.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddingAdapter
from kronos_engine.ports.secrets import ScopedSecret


class _Transport:
    def __init__(
        self,
        *,
        status: int = 200,
        payload: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.status = status
        self.payload = payload if payload is not None else {
            "data": [
                {"embedding": [0.25, 0.5, 0.75], "index": 0},
                {"embedding": [1.0, 0.0, 0.0], "index": 1},
            ]
        }
        self.error = error

    def get(self, url: str, timeout: float) -> tuple[int, dict[str, object]]:
        self.calls.append({"method": "get", "url": url, "timeout": timeout})
        return 200, {}

    def post(
        self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, object]]:
        self.calls.append(
            {"method": "post", "url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        return self.status, self.payload


def test_embed_posts_openai_shape_with_bearer_secret() -> None:
    transport = _Transport()
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="https://openrouter.ai/api/v1",
        model_id="text-embedding-3-small",
        billed=True,
        secret=ScopedSecret(value="sk-live-embed", ttl_seconds=30),
        transport=transport,
    )
    assert adapter.available("document") is True
    assert adapter.available("code") is True
    vectors = adapter.embed(["alpha", "beta"], kind="document")
    assert vectors == [[0.25, 0.5, 0.75], [1.0, 0.0, 0.0]]
    posted = transport.calls[0]
    assert posted["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert posted["json"] == {"model": "text-embedding-3-small", "input": ["alpha", "beta"]}
    headers = posted["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer sk-live-embed"


def test_embed_omits_authorization_when_no_secret_and_allows_loopback() -> None:
    transport = _Transport(
        payload={"data": [{"embedding": [0.1, 0.2], "index": 0}]},
    )
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="http://127.0.0.1:11434/v1",
        model_id="nomic-embed-text",
        billed=False,
        secret=None,
        transport=transport,
    )
    vectors = adapter.embed(["hello"], kind="code")
    assert vectors == [[0.1, 0.2]]
    headers = transport.calls[0]["headers"]
    assert isinstance(headers, dict)
    assert "Authorization" not in headers


def test_http_and_parse_failures_return_none_without_raising() -> None:
    failing = OpenAICompatibleEmbeddingAdapter(
        base_url="https://api.openai.com/v1",
        model_id="text-embedding-3-small",
        billed=True,
        secret=ScopedSecret(value="sk-fail", ttl_seconds=30),
        transport=_Transport(status=500, payload={}),
    )
    assert failing.embed(["hello"], kind="document") is None

    malformed = OpenAICompatibleEmbeddingAdapter(
        base_url="https://api.openai.com/v1",
        model_id="text-embedding-3-small",
        billed=True,
        secret=None,
        transport=_Transport(payload={"data": "nope"}),
    )
    assert malformed.embed(["hello"], kind="document") is None

    exploding = OpenAICompatibleEmbeddingAdapter(
        base_url="https://api.openai.com/v1",
        model_id="text-embedding-3-small",
        billed=False,
        secret=None,
        transport=_Transport(error=OSError("offline")),
    )
    assert exploding.embed(["hello"], kind="document") is None


def _embed_payload(payload: object) -> list[list[float]] | None:
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="https://api.openai.com/v1",
        model_id="text-embedding-3-small",
        billed=False,
        secret=None,
        transport=_Transport(payload=payload),  # type: ignore[arg-type]
    )
    try:
        result = adapter.embed(["alpha", "beta"], kind="document")
    except Exception as exc:
        raise AssertionError(f"embed raised {type(exc).__name__}: {exc}") from exc
    if result is None:
        return None
    return [list(row) for row in result]


def test_malformed_embedding_values_return_none_without_raising() -> None:
    assert _embed_payload(["not", "a", "dict"]) is None
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, float("nan")], "index": 0},
                    {"embedding": [0.0, 1.0], "index": 1},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, float("inf")], "index": 0},
                    {"embedding": [0.0, 1.0], "index": 1},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0], "index": 0},
                    {"embedding": [1.0, 2.0], "index": 1},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, 2.0], "index": 0},
                    {"embedding": [3.0, 4.0], "index": 0},
                ]
            }
        )
        is None
    )
    assert (
        _embed_payload(
            {
                "data": [
                    {"embedding": [1.0, 2.0], "index": 0},
                    {"embedding": [3.0, 4.0], "index": 5},
                ]
            }
        )
        is None
    )
