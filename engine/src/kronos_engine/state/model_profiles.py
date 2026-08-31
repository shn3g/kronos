# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite persistence for providers, profiles, and role assignments. No secrets."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from kronos_engine.domain.models import ModelProfile, ResourceLimits
from kronos_engine.ports.model_registry import ProviderConfig, RoleAssignments


class SqliteModelRegistry:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_provider(self, provider: ProviderConfig) -> None:
        self._conn.execute(
            """
            INSERT INTO model_providers(id, kind, display_name, base_url, billed, secret_ref)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
                display_name = excluded.display_name,
                base_url = excluded.base_url,
                billed = excluded.billed,
                secret_ref = excluded.secret_ref
            """,
            (
                provider.id,
                provider.kind,
                provider.display_name,
                provider.base_url,
                1 if provider.billed else 0,
                provider.secret_ref,
            ),
        )
        self._conn.commit()

    def list_providers(self) -> Sequence[ProviderConfig]:
        rows = self._conn.execute(
            "SELECT id, kind, display_name, base_url, billed, secret_ref "
            "FROM model_providers ORDER BY display_name, id"
        ).fetchall()
        return tuple(
            ProviderConfig(
                id=row["id"],
                kind=row["kind"],
                display_name=row["display_name"],
                base_url=row["base_url"],
                billed=bool(row["billed"]),
                secret_ref=row["secret_ref"],
                api_key=None,
            )
            for row in rows
        )

    def save_profile(self, profile: ModelProfile) -> None:
        self._conn.execute(
            """
            INSERT INTO model_profiles(
                id, display_name, role, provider_id, model_id, billed,
                approved_fallbacks_json, limits_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                role = excluded.role,
                provider_id = excluded.provider_id,
                model_id = excluded.model_id,
                billed = excluded.billed,
                approved_fallbacks_json = excluded.approved_fallbacks_json,
                limits_json = excluded.limits_json
            """,
            (
                profile.id,
                profile.display_name,
                profile.role,
                profile.provider_id,
                profile.model_id,
                1 if profile.billed else 0,
                json.dumps(list(profile.approved_fallbacks)),
                json.dumps(
                    {
                        "max_tokens": profile.limits.max_tokens,
                        "max_attempts": profile.limits.max_attempts,
                        "timeout_seconds": profile.limits.timeout_seconds,
                        "cost_ceiling": profile.limits.cost_ceiling,
                    }
                ),
            ),
        )
        self._conn.commit()

    def list_profiles(self) -> Sequence[ModelProfile]:
        rows = self._conn.execute(
            "SELECT id, display_name, role, provider_id, model_id, billed, "
            "approved_fallbacks_json, limits_json FROM model_profiles ORDER BY display_name, id"
        ).fetchall()
        return tuple(_profile_from_row(row) for row in rows)

    def save_assignments(self, assignments: RoleAssignments) -> None:
        for role, profile_id in assignments.as_dict().items():
            if profile_id is None:
                self._conn.execute("DELETE FROM model_assignments WHERE role = ?", (role,))
                continue
            self._conn.execute(
                """
                INSERT INTO model_assignments(role, profile_id) VALUES (?, ?)
                ON CONFLICT(role) DO UPDATE SET profile_id = excluded.profile_id
                """,
                (role, profile_id),
            )
        self._conn.commit()

    def load_assignments(self) -> RoleAssignments:
        rows = {
            row["role"]: row["profile_id"]
            for row in self._conn.execute("SELECT role, profile_id FROM model_assignments")
        }
        return RoleAssignments(
            planner=rows.get("planner"),
            coder=rows.get("coder"),
            reviewer=rows.get("reviewer"),
            embedding=rows.get("embedding"),
        )


def _profile_from_row(row: sqlite3.Row) -> ModelProfile:
    limits_raw = json.loads(row["limits_json"])
    fallbacks = json.loads(row["approved_fallbacks_json"])
    return ModelProfile(
        id=row["id"],
        display_name=row["display_name"],
        role=row["role"],
        provider_id=row["provider_id"],
        model_id=row["model_id"],
        billed=bool(row["billed"]),
        approved_fallbacks=tuple(fallbacks),
        limits=ResourceLimits(
            max_tokens=int(limits_raw["max_tokens"]),
            max_attempts=int(limits_raw["max_attempts"]),
            timeout_seconds=float(limits_raw["timeout_seconds"]),
            cost_ceiling=float(limits_raw["cost_ceiling"]),
        ),
    )
