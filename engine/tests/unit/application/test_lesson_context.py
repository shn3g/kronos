# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stored memory hits for the task title land in executor lesson_summaries."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.test_goal_to_integration_pr import GoalHarness, ScriptedExecutor

from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.application.dispatch import DispatchService
from kronos_engine.indexing.service import IndexingService
from kronos_engine.memory.procedural import persist_record
from kronos_engine.memory.records import MemoryKind, MemoryRecord, MemoryStatus
from kronos_engine.skills.catalog import SkillCatalog
from kronos_engine.skills.quarantine import FixtureSkillSource


class _Capture(ScriptedExecutor):
    def __init__(self) -> None:
        super().__init__("happy")
        self.last = None

    def run(self, request, sandbox):  # type: ignore[no-untyped-def]
        self.last = request
        return super().run(request, sandbox)


def test_matching_memory_record_appears_in_lesson_summaries(tmp_path: Path) -> None:
    capture = _Capture()
    harness = GoalHarness(tmp_path, "happy", executor=capture)
    harness.setup_goal()
    persist_record(
        harness.conn,
        MemoryRecord(
            id="mem-fix-add",
            kind=MemoryKind.procedural.value,
            text="When fixing add, cover the zero path before changing pkg math.",
            source_sha="abc123",
            outcome="helpful",
            confidence=0.8,
            helpful=1,
            harmful=0,
            status=MemoryStatus.active,
            independent_sources=("abc123",),
            skill_id=None,
            created_at="2026-09-01T00:00:00+00:00",
            provenance={},
        ),
        embeddings=None,
    )
    catalog = SkillCatalog(
        harness.conn,
        skills_root=tmp_path / "library",
        store_dir=tmp_path / "skill-store",
        source=FixtureSkillSource({}),
    )
    harness.dispatch = DispatchService(
        harness.store,
        harness.repos,
        harness.leases,
        harness.recorder,
        IndexingService(harness.paths),
        capture,
        lambda worktree: ProcessJailSandbox(worktree),
        harness.paths.cache,
        clock=lambda: harness.now,
        skills=catalog,
    )
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is True
    executed = harness.dispatch.execute(claimed, phase="red")
    assert executed.ok is True
    assert capture.last is not None
    lessons = capture.last.context.lesson_summaries
    assert any("When fixing add" in item for item in lessons)
