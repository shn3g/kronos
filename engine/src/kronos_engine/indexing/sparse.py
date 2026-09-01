# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite FTS5/BM25 sparse index. One database file per repository id."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from kronos_engine.ports.index_store import IndexedChunk, Relation

_TOKEN = re.compile(r"[A-Za-z0-9_]+")


class SqliteIndexStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def replace_all(self, chunks: Sequence[IndexedChunk], relations: Sequence[Relation]) -> None:
        self._conn.execute("DELETE FROM vectors")
        self._conn.execute("DELETE FROM relations")
        self._conn.execute("DELETE FROM chunks_fts")
        self._conn.execute("DELETE FROM chunks")
        self._conn.execute("DELETE FROM working_files")
        self.upsert(chunks)
        self.replace_relations(relations)

    def delete_paths(self, paths: Sequence[str]) -> None:
        for path in paths:
            posix = path.replace("\\", "/")
            rows = self._conn.execute(
                "SELECT chunk_id FROM chunks WHERE path = ?", (posix,)
            ).fetchall()
            for row in rows:
                self._conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (row["chunk_id"],))
                self._conn.execute("DELETE FROM vectors WHERE chunk_id = ?", (row["chunk_id"],))
            self._conn.execute("DELETE FROM chunks WHERE path = ?", (posix,))
            self._conn.execute(
                "DELETE FROM relations WHERE src_path = ? OR dst_path = ?", (posix, posix)
            )
        self._conn.commit()

    def upsert(self, chunks: Sequence[IndexedChunk]) -> None:
        for chunk in chunks:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO chunks (
                    chunk_id, path, start_line, end_line, symbol, kind, language,
                    git_commit, content_hash, text, trust
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.path,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.symbol,
                    chunk.kind,
                    chunk.language,
                    chunk.commit,
                    chunk.content_hash,
                    chunk.text,
                    chunk.trust,
                ),
            )
            self._conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk.chunk_id,))
            self._conn.execute(
                """
                INSERT INTO chunks_fts (chunk_id, path, symbol, text, kind)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chunk.chunk_id, chunk.path, chunk.symbol or "", chunk.text, chunk.kind),
            )
        self._conn.commit()

    def replace_relations(self, relations: Sequence[Relation]) -> None:
        self._conn.execute("DELETE FROM relations")
        self._conn.executemany(
            "INSERT INTO relations (src_path, dst_path, rel_type) VALUES (?, ?, ?)",
            [(item.src_path, item.dst_path, item.rel_type) for item in relations],
        )
        self._conn.commit()

    def list_chunks(self) -> Sequence[IndexedChunk]:
        rows = self._conn.execute("SELECT * FROM chunks ORDER BY path, start_line").fetchall()
        return tuple(_row_to_chunk(row) for row in rows)

    def chunks_for_path(self, path: str) -> Sequence[IndexedChunk]:
        rows = self._conn.execute(
            "SELECT * FROM chunks WHERE path = ? ORDER BY start_line",
            (path.replace("\\", "/"),),
        ).fetchall()
        return tuple(_row_to_chunk(row) for row in rows)

    def get_chunk(self, chunk_id: str) -> IndexedChunk | None:
        row = self._conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return None if row is None else _row_to_chunk(row)

    def search_sparse(self, query: str, limit: int) -> Sequence[str]:
        match = _fts_query(query)
        if match is None:
            return ()
        rows = self._conn.execute(
            """
            SELECT chunk_id FROM chunks_fts
            WHERE chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts), chunk_id
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return tuple(row["chunk_id"] for row in rows)

    def indexed_commit(self) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'git_commit'").fetchone()
        return None if row is None else str(row["value"])

    def set_indexed_commit(self, commit: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('git_commit', ?)", (commit,)
        )
        self._conn.commit()

    def working_file_matches(self, path: str, mtime_ns: int, size: int) -> bool:
        row = self._conn.execute(
            "SELECT mtime_ns, size FROM working_files WHERE path = ?",
            (path.replace("\\", "/"),),
        ).fetchone()
        if row is None:
            return False
        return int(row["mtime_ns"]) == mtime_ns and int(row["size"]) == size

    def set_working_file(self, path: str, mtime_ns: int, size: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO working_files (path, mtime_ns, size) VALUES (?, ?, ?)",
            (path.replace("\\", "/"), mtime_ns, size),
        )
        self._conn.commit()

    def clear_working_file(self, path: str) -> None:
        self._conn.execute(
            "DELETE FROM working_files WHERE path = ?", (path.replace("\\", "/"),)
        )
        self._conn.commit()

    def list_relations(self) -> Sequence[Relation]:
        rows = self._conn.execute("SELECT src_path, dst_path, rel_type FROM relations").fetchall()
        return tuple(
            Relation(src_path=row["src_path"], dst_path=row["dst_path"], rel_type=row["rel_type"])
            for row in rows
        )

    def connection(self) -> sqlite3.Connection:
        return self._conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            symbol TEXT,
            kind TEXT NOT NULL,
            language TEXT NOT NULL,
            git_commit TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            text TEXT NOT NULL,
            trust TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            path,
            symbol,
            text,
            kind,
            tokenize='porter unicode61'
        );
        CREATE TABLE IF NOT EXISTS relations (
            src_path TEXT NOT NULL,
            dst_path TEXT NOT NULL,
            rel_type TEXT NOT NULL,
            PRIMARY KEY (src_path, dst_path, rel_type)
        );
        CREATE TABLE IF NOT EXISTS vectors (
            chunk_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            dim INTEGER NOT NULL,
            embedding BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS working_files (
            path TEXT PRIMARY KEY,
            mtime_ns INTEGER NOT NULL,
            size INTEGER NOT NULL
        );
        """
    )
    conn.commit()


def _row_to_chunk(row: sqlite3.Row) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=row["chunk_id"],
        path=row["path"],
        start_line=int(row["start_line"]),
        end_line=int(row["end_line"]),
        symbol=row["symbol"],
        kind=row["kind"],
        language=row["language"],
        commit=row["git_commit"],
        content_hash=row["content_hash"],
        text=row["text"],
        trust=row["trust"],
    )


def _fts_query(query: str) -> str | None:
    tokens = _TOKEN.findall(query)
    if not tokens:
        return None
    return " OR ".join('"' + token.replace('"', "") + '"' for token in tokens)
