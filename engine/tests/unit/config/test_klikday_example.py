# SPDX-License-Identifier: AGPL-3.0-or-later
"""Klikday example pack is schema-valid and does not encode Hermes."""

from __future__ import annotations

from pathlib import Path

from kronos_engine.domain.policy import parse_policy
from kronos_engine.domain.policy_yaml import parse_simple_yaml
from kronos_engine.memory.procedural import ProceduralStore, parse_klikday_lessons
from kronos_engine.memory.records import MemoryStatus
from kronos_engine.state.database import Database

REPO_ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = REPO_ROOT / "examples" / "klikday"


def test_klikday_example_policy_parses_with_main_openclaw() -> None:
    text = (EXAMPLE / "config.yaml").read_text(encoding="utf-8")
    raw = parse_simple_yaml(text)
    assert isinstance(raw, dict)
    policy = parse_policy(raw)
    assert policy.branches.integration == "main-openclaw"
    assert policy.branches.protected == "main"
    assert policy.autonomy.mode in {"observe", "shadow"}
    assert policy.autonomy.freeze is True
    assert policy.autonomy.invent_issues is False
    assert policy.autonomy.refill_enabled is False
    assert "backend/bookings" in policy.paths.locked_prefixes
    assert policy.wip.ready == 2
    assert policy.wip.running == 3
    assert policy.budgets.dry_run_meters is False
    assert "hermes" not in text.lower()
    assert "coder_may_merge" not in text
    assert "pulse_may_merge" not in text


def test_klikday_example_lessons_import_as_disabled_candidates(tmp_path: Path) -> None:
    text = (EXAMPLE / "lessons.yaml").read_text(encoding="utf-8")
    parsed = parse_klikday_lessons(text)
    assert parsed
    db = Database(tmp_path / "kronos.sqlite3")
    imported = ProceduralStore(db.connect()).import_klikday_lessons(text)
    assert imported
    assert {item.status for item in imported} == {MemoryStatus.disabled_candidate}
    assert all(item.provenance.get("import") == "klikday" for item in imported)
