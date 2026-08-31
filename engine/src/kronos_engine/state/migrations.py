# SPDX-License-Identifier: AGPL-3.0-or-later
"""Numbered, idempotent SQLite migrations."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );

        CREATE TRIGGER events_forbid_update
        BEFORE UPDATE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events are append-only');
        END;

        CREATE TRIGGER events_forbid_delete
        BEFORE DELETE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events are append-only');
        END;

        CREATE TABLE outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            dispatched_at TEXT
        );

        CREATE TABLE leases (
            resource_key TEXT PRIMARY KEY,
            holder_id TEXT NOT NULL,
            fence_token INTEGER NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE repositories (
            id TEXT PRIMARY KEY
        );

        CREATE TABLE goals (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL REFERENCES repositories(id)
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE repositories_new (
            id TEXT PRIMARY KEY,
            realpath TEXT NOT NULL UNIQUE,
            origin TEXT,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'paused', 'disabled')),
            policy_json TEXT NOT NULL,
            enrolled_at TEXT NOT NULL
        );

        DROP TABLE goals;
        DROP TABLE repositories;
        ALTER TABLE repositories_new RENAME TO repositories;

        CREATE TABLE goals (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL REFERENCES repositories(id)
        );
        """,
    ),
    (
        3,
        """
        CREATE TABLE model_providers (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            display_name TEXT NOT NULL,
            base_url TEXT,
            billed INTEGER NOT NULL CHECK (billed IN (0, 1)),
            secret_ref TEXT NOT NULL
        );

        CREATE TABLE model_profiles (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            provider_id TEXT NOT NULL REFERENCES model_providers(id),
            model_id TEXT NOT NULL,
            billed INTEGER NOT NULL CHECK (billed IN (0, 1)),
            approved_fallbacks_json TEXT NOT NULL,
            limits_json TEXT NOT NULL
        );

        CREATE TABLE model_assignments (
            role TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES model_profiles(id)
        );
        """,
    ),
)


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, datetime.now(tz=UTC).isoformat()),
        )
        conn.commit()
