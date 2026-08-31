# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local embedding port. Vectors are disposable; missing models degrade."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

EMBEDDING_KIND_CODE = "code"
EMBEDDING_KIND_DOCUMENT = "document"


class EmbeddingPort(Protocol):
    def available(self, kind: str) -> bool: ...

    def embed(
        self, texts: Sequence[str], *, kind: str
    ) -> Sequence[Sequence[float]] | None: ...
