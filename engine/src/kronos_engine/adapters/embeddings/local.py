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


@dataclass(frozen=True, slots=True)
class EmbeddingModelConfig:
    model_id: str
    license: str
    filename: str
    sha256: str


class LocalEmbeddingAdapter:
    """Looks up pinned ONNX files under a local directory. No network I/O."""

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

    def available(self, kind: str) -> bool:
        return self._load_session(kind) is not None

    def embed(self, texts: Sequence[str], *, kind: str) -> Sequence[Sequence[float]] | None:
        session = self._load_session(kind)
        if session is None:
            return None
        run = getattr(session, "run", None)
        get_inputs = getattr(session, "get_inputs", None)
        if run is None or get_inputs is None:
            return None
        inputs = get_inputs()
        if len(inputs) != 1:
            return None
        spec = inputs[0]
        shape = list(spec.shape)
        if len(shape) != 2 or not isinstance(shape[1], int):
            return None
        try:
            numpy = cast(Any, importlib.import_module("numpy"))
        except ImportError:
            return None
        features = numpy.asarray(_hash_features(texts, int(shape[1])), dtype=numpy.float32)
        outputs = run(None, {spec.name: features})
        if not outputs:
            return None
        return [[float(value) for value in row] for row in outputs[0]]

    def _spec(self, kind: str) -> EmbeddingModelConfig | None:
        if kind == "document":
            return self._document
        if kind == "code":
            if _is_minilm(self._code):
                return None
            return self._code
        return None

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
        except (OSError, ValueError, RuntimeError):
            return None
        loaded: object = session
        self._sessions[kind] = loaded
        return loaded


def _is_minilm(spec: EmbeddingModelConfig) -> bool:
    return spec.model_id == DOCUMENT_MODEL_ID or spec.filename == DOCUMENT_FILENAME


def _hash_features(texts: Sequence[str], dim: int) -> list[list[float]]:
    rows: list[list[float]] = []
    for text in texts:
        row = [0.0] * dim
        payload = text.encode("utf-8") or b"\x00"
        for index, byte in enumerate(payload):
            row[index % dim] += (byte + 1) / 256.0
        norm = sum(value * value for value in row) ** 0.5
        if norm > 0.0:
            row = [value / norm for value in row]
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
