# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pinned local embedding adapter. Never downloads weights."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

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

    def available(self, kind: str) -> bool:
        spec = self._spec(kind)
        if spec is None:
            return False
        path = self._models_dir / spec.filename
        if not path.is_file():
            return False
        if spec.sha256 and _sha256(path) != spec.sha256.lower():
            return False
        return False

    def embed(self, texts: Sequence[str], *, kind: str) -> Sequence[Sequence[float]] | None:
        _ = texts
        if not self.available(kind):
            return None
        return None

    def _spec(self, kind: str) -> EmbeddingModelConfig | None:
        if kind == "document":
            return self._document
        if kind == "code":
            return self._code
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
