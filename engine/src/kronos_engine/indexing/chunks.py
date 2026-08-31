# SPDX-License-Identifier: AGPL-3.0-or-later
"""UTF-8 file chunking plus symbol windows."""

from __future__ import annotations

import hashlib

from kronos_engine.indexing.languages import extract_symbols
from kronos_engine.indexing.scanner import ScannedFile
from kronos_engine.ports.index_store import IndexedChunk

_WINDOW = 80
_OVERLAP = 10
_FILE_CHUNK_LIMIT = 200


def chunk_text(scanned: ScannedFile, *, commit: str) -> tuple[IndexedChunk, ...]:
    lines = scanned.text.splitlines()
    if not lines and scanned.text == "":
        lines = []
    trust = "tracked"
    chunks: list[IndexedChunk] = []
    symbols = extract_symbols(scanned.text, scanned.language)
    for symbol in symbols:
        start = max(1, symbol.start_line)
        end = min(len(lines), max(start, symbol.end_line))
        body = "\n".join(lines[start - 1 : end])
        chunks.append(
            _chunk(
                scanned,
                commit=commit,
                start=start,
                end=end,
                text=body,
                symbol=symbol.name,
                kind=symbol.kind,
                trust=trust,
            )
        )
    kind = "document" if scanned.language == "markdown" else "file"
    if len(lines) <= _FILE_CHUNK_LIMIT:
        chunks.append(
            _chunk(
                scanned,
                commit=commit,
                start=1 if lines else 1,
                end=max(1, len(lines)),
                text=scanned.text,
                symbol=None,
                kind=kind,
                trust=trust,
            )
        )
    else:
        start = 1
        while start <= len(lines):
            end = min(len(lines), start + _WINDOW - 1)
            body = "\n".join(lines[start - 1 : end])
            chunks.append(
                _chunk(
                    scanned,
                    commit=commit,
                    start=start,
                    end=end,
                    text=body,
                    symbol=None,
                    kind=kind,
                    trust=trust,
                )
            )
            if end == len(lines):
                break
            start = end - _OVERLAP + 1
    return tuple(chunks)


def _chunk(
    scanned: ScannedFile,
    *,
    commit: str,
    start: int,
    end: int,
    text: str,
    symbol: str | None,
    kind: str,
    trust: str,
) -> IndexedChunk:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = hashlib.sha256(
        f"{scanned.path}:{start}:{end}:{digest}".encode()
    ).hexdigest()[:24]
    return IndexedChunk(
        chunk_id=identity,
        path=scanned.path,
        start_line=start,
        end_line=end,
        symbol=symbol,
        kind=kind,
        language=scanned.language,
        commit=commit,
        content_hash=digest,
        text=text,
        trust=trust,
    )
