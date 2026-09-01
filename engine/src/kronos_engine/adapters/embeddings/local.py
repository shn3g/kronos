# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pinned local embedding adapter. Never downloads weights."""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

DOCUMENT_MODEL_ID = "all-MiniLM-L6-v2"
DOCUMENT_MODEL_LICENSE = "Apache-2.0"
CODE_MODEL_ID = "kronos-code-local"
CODE_MODEL_LICENSE = "AGPL-3.0-or-later"
DOCUMENT_FILENAME = "all-MiniLM-L6-v2.onnx"
CODE_FILENAME = "code.onnx"
TOKENIZER_FILENAME = "tokenizer.json"
DEFAULT_SEQUENCE_LENGTH = 256


@dataclass(frozen=True, slots=True)
class EmbeddingModelConfig:
    model_id: str
    license: str
    filename: str
    sha256: str


class LocalEmbeddingAdapter:
    """Looks up pinned ONNX files and tokenizer.json under a local directory. No network I/O."""

    def __init__(
        self,
        models_dir: Path,
        *,
        document: EmbeddingModelConfig | None = None,
        code: EmbeddingModelConfig | None = None,
    ) -> None:
        self._models_dir = models_dir
        self._document = document or EmbeddingModelConfig(
            model_id=DOCUMENT_MODEL_ID,
            license=DOCUMENT_MODEL_LICENSE,
            filename=DOCUMENT_FILENAME,
            sha256="",
        )
        self._code = code or EmbeddingModelConfig(
            model_id=CODE_MODEL_ID,
            license=CODE_MODEL_LICENSE,
            filename=CODE_FILENAME,
            sha256="",
        )
        self._sessions: dict[str, object] = {}
        self._tokenizer: object | None = None

    def available(self, kind: str) -> bool:
        return self._load_session(kind) is not None and self._load_tokenizer() is not None

    def embed(self, texts: Sequence[str], *, kind: str) -> Sequence[Sequence[float]] | None:
        session = self._load_session(kind)
        tokenizer = self._load_tokenizer()
        if session is None or tokenizer is None:
            return None
        run = getattr(session, "run", None)
        get_inputs = getattr(session, "get_inputs", None)
        if run is None or get_inputs is None:
            return None
        inputs = list(get_inputs())
        if not inputs:
            return None
        try:
            numpy = cast(Any, importlib.import_module("numpy"))
        except ImportError:
            return None
        seq_len = _sequence_length(inputs)
        try:
            input_ids, attention_mask = _tokenize(tokenizer, texts, seq_len)
        except Exception:
            return None
        ids = numpy.asarray(input_ids, dtype=numpy.int64)
        mask = numpy.asarray(attention_mask, dtype=numpy.int64)
        feeds: dict[str, Any] = {}
        for spec in inputs:
            name = str(getattr(spec, "name", ""))
            if name == "attention_mask":
                feeds[name] = mask
            elif name == "token_type_ids":
                feeds[name] = numpy.zeros_like(ids)
            else:
                feeds[name] = ids
        try:
            outputs = run(None, feeds)
        except Exception:
            return None
        if not outputs:
            return None
        hidden = numpy.asarray(outputs[0])
        pooled = _pool(hidden, mask)
        if pooled is None:
            return None
        return [[float(value) for value in row] for row in pooled]

    def _spec(self, kind: str) -> EmbeddingModelConfig | None:
        if kind == "document":
            return self._document
        if kind == "code":
            if _is_minilm(self._code):
                return None
            return self._code
        return None

    def _load_tokenizer(self) -> object | None:
        if self._tokenizer is not None:
            return self._tokenizer
        path = self._models_dir / TOKENIZER_FILENAME
        if not path.is_file():
            return None
        try:
            tokenizers = cast(Any, importlib.import_module("tokenizers"))
            loaded: object = tokenizers.Tokenizer.from_file(str(path.resolve()))
        except Exception:
            return None
        self._tokenizer = loaded
        return loaded

    def _load_session(self, kind: str) -> object | None:
        cached = self._sessions.get(kind)
        if cached is not None:
            return cached
        spec = self._spec(kind)
        if spec is None:
            return None
        path = self._models_dir / spec.filename
        if not path.is_file():
            return None
        if spec.sha256 and _sha256(path) != spec.sha256.lower():
            return None
        try:
            ort = cast(Any, importlib.import_module("onnxruntime"))
        except ImportError:
            return None
        options = ort.SessionOptions()
        try:
            session = ort.InferenceSession(
                str(path.resolve()),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception:
            return None
        loaded: object = session
        self._sessions[kind] = loaded
        return loaded


def _is_minilm(spec: EmbeddingModelConfig) -> bool:
    return spec.model_id == DOCUMENT_MODEL_ID or spec.filename == DOCUMENT_FILENAME


def _sequence_length(inputs: Sequence[Any]) -> int:
    for spec in inputs:
        shape = list(getattr(spec, "shape", ()))
        if len(shape) >= 2 and isinstance(shape[1], int) and shape[1] > 0:
            return int(shape[1])
    return DEFAULT_SEQUENCE_LENGTH


def _tokenize(
    tokenizer: object, texts: Sequence[str], seq_len: int
) -> tuple[list[list[int]], list[list[int]]]:
    pad_id = _pad_id(tokenizer)
    enable_truncation = getattr(tokenizer, "enable_truncation", None)
    enable_padding = getattr(tokenizer, "enable_padding", None)
    if callable(enable_truncation):
        enable_truncation(max_length=seq_len)
    if callable(enable_padding):
        enable_padding(direction="right", length=seq_len, pad_id=pad_id, pad_token="[PAD]")
    encode_batch = getattr(tokenizer, "encode_batch")
    encodings = encode_batch(list(texts))
    ids: list[list[int]] = []
    masks: list[list[int]] = []
    for encoding in encodings:
        token_ids = [int(value) for value in encoding.ids][:seq_len]
        mask = [int(value) for value in encoding.attention_mask][:seq_len]
        if len(token_ids) < seq_len:
            pad = seq_len - len(token_ids)
            token_ids.extend([pad_id] * pad)
            mask.extend([0] * pad)
        ids.append(token_ids)
        masks.append(mask)
    return ids, masks


def _pad_id(tokenizer: object) -> int:
    token_to_id = getattr(tokenizer, "token_to_id", None)
    if callable(token_to_id):
        for token in ("[PAD]", "<pad>", "[pad]"):
            value = token_to_id(token)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return 0


def _pool(hidden: Any, mask: Any) -> Any | None:
    if getattr(hidden, "ndim", None) == 2:
        return hidden
    if getattr(hidden, "ndim", None) != 3:
        return None
    weights = mask.astype(hidden.dtype)[:, :, None]
    summed = (hidden * weights).sum(axis=1)
    counts = weights.sum(axis=1).clip(min=1.0)
    return summed / counts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
