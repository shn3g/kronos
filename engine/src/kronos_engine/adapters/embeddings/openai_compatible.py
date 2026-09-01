# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI-compatible embeddings. HTTP failures degrade to sparse retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from urllib.parse import urlparse

from kronos_engine.adapters.models.openai_compatible import HttpTransport, UrllibTransport
from kronos_engine.ports.secrets import ScopedSecret

_EMBED_KINDS = frozenset({"document", "code"})


class OpenAICompatibleEmbeddingAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        billed: bool,
        secret: ScopedSecret | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._billed = billed
        self._secret = secret
        self._transport = transport or UrllibTransport()

    def available(self, kind: str) -> bool:
        if kind not in _EMBED_KINDS or not self._model_id.strip():
            return False
        return _is_http_url(self._base_url)

    def embed(self, texts: Sequence[str], *, kind: str) -> Sequence[Sequence[float]] | None:
        if not self.available(kind):
            return None
        headers: dict[str, str] = {"Content-Type": "application/json"}
        try:
            if self._secret is not None:
                headers["Authorization"] = f"Bearer {self._secret.require_fresh()}"
            status, payload = self._transport.post(
                f"{self._base_url}/embeddings",
                {"model": self._model_id, "input": list(texts)},
                headers,
                30.0,
            )
        except Exception:
            return None
        if status != 200:
            return None
        try:
            return _parse_embeddings(payload, expected=len(texts))
        except Exception:
            return None


def _is_http_url(url: str) -> bool:
    return urlparse(url).scheme.lower() in {"http", "https"}


def _parse_embeddings(payload: object, *, expected: int) -> list[list[float]] | None:
    try:
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, list):
            return None
        rows: list[tuple[int, list[float]]] = []
        for position, item in enumerate(data):
            if not isinstance(item, dict):
                return None
            raw_index = item.get("index", position)
            if not isinstance(raw_index, int) or isinstance(raw_index, bool) or raw_index < 0:
                return None
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                return None
            values: list[float] = []
            for value in embedding:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return None
                number = float(value)
                if not isfinite(number):
                    return None
                values.append(number)
            rows.append((raw_index, values))
        rows.sort(key=lambda pair: pair[0])
        if [index for index, _vector in rows] != list(range(expected)):
            return None
        vectors = [vector for _index, vector in rows]
        if expected == 0:
            return []
        width = len(vectors[0])
        if width == 0 or any(len(vector) != width for vector in vectors):
            return None
        return vectors
    except Exception:
        return None
