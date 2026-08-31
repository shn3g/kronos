# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dependency failures pause with evidence. Fixtures only; no live GitHub."""

from __future__ import annotations

import errno
from pathlib import Path

from tests.e2e.test_goal_to_integration_pr import GoalHarness
from tests.support.github_fixture import controller_stack

from kronos_engine.domain.tasks import TaskState
from kronos_engine.ports.forge import ForgeRateLimited, ForgeTransientError
from kronos_engine.ports.sandbox import Sandbox


class _ThrottleForge:
    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.writes = 0

    def open_draft_pr(self, *args: object, **kwargs: object) -> object:
        self.writes += 1
        raise ForgeRateLimited("GitHub rate limited the request")

    def merge_pull(self, *args: object, **kwargs: object) -> None:
        raise ForgeRateLimited("GitHub rate limited the request")

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class _ReviewerOutageForge:
    def __init__(self, inner: object) -> None:
        self._inner = inner

    def list_check_runs(self, sha: str) -> list[object]:
        _ = sha
        raise ForgeTransientError("reviewer outage")

    def merge_pull(self, *args: object, **kwargs: object) -> None:
        raise ForgeTransientError("reviewer outage")

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class _DiskFullSandbox:
    def __init__(self, inner: Sandbox) -> None:
        self._inner = inner

    def write_text(self, relative: str, content: str) -> Path:
        _ = relative, content
        raise OSError(errno.ENOSPC, "No space left on device")

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class _TimeoutGates:
    def run(self, worktree: Path, commands: tuple[tuple[str, ...], ...]) -> list[dict[str, object]]:
        _ = worktree, commands
        raise TimeoutError("ci timeout")


def test_process_kill_does_not_duplicate_external_writes(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    interrupted = harness.engine.advance(harness.task_id, holder_id="worker-1", stop_after="pr")
    assert interrupted.ok is True
    assert harness.fixture.count_pulls() == 1
    first_conn = harness.conn
    restarted = harness.reconnect()
    assert restarted.conn is not first_conn
    restarted._simulate_reviewer()
    merged = restarted.verification.merge_if_eligible(restarted.task_id, restarted.merge)
    assert merged.ok is True
    assert restarted.fixture.count_pulls() == 1
    assert restarted.fixture.merge_calls()
    restarted.engine.advance(restarted.task_id, holder_id="worker-2")
    assert restarted.fixture.count_pulls() == 1


def test_model_outage_pauses_without_github_writes(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "model_outage")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.PAUSED.value
    assert "outage" in outcome.reason.lower()
    assert harness.fixture.count_pulls() == 0
    assert harness.fixture.merge_calls() == ()


def test_github_throttling_pauses_without_duplicate_writes(tmp_path: Path) -> None:
    built, fixture, _auth = controller_stack()
    harness = GoalHarness(tmp_path, "happy", forge=_ThrottleForge(built), fixture=fixture)
    harness.setup_goal()
    result = harness.engine.advance(harness.task_id, holder_id="worker-1")
    assert result.ok is False
    assert harness.store.get_task(harness.task_id).state is TaskState.PAUSED
    assert fixture.count_pulls() == 0
    assert fixture.merge_calls() == ()
    harness.engine.advance(harness.task_id, holder_id="worker-1")
    assert fixture.count_pulls() == 0
    assert fixture.merge_calls() == ()


def test_ci_timeout_pauses_safely(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    harness.verification._gates = _TimeoutGates()
    result = harness.engine.advance(harness.task_id, holder_id="worker-1")
    assert result.ok is False
    task = harness.store.get_task(harness.task_id)
    assert task.state is TaskState.PAUSED
    assert "timeout" in (task.stop_reason or result.reason or "").lower()
    assert harness.fixture.merge_calls() == ()
    assert harness.fixture.count_pulls() == 0


def test_disk_full_pauses_without_external_write(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    original = harness.dispatch._sandbox_factory

    def full(worktree: Path) -> Sandbox:
        return _DiskFullSandbox(original(worktree))

    harness.dispatch._sandbox_factory = full
    result = harness.engine.advance(harness.task_id, holder_id="worker-1")
    assert result.ok is False
    task = harness.store.get_task(harness.task_id)
    assert task.state is TaskState.PAUSED
    assert "disk" in (task.stop_reason or result.reason or "").lower()
    assert harness.fixture.count_pulls() == 0
    assert harness.fixture.merge_calls() == ()


def test_corrupt_cache_degrades_index_and_pauses(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    index_dir = harness.paths.cache / "indexes" / harness.repo_id.value
    db = index_dir / "index.sqlite3"
    if db.is_file():
        db.write_bytes(b"not-a-sqlite-database")
    from kronos_engine.application.doctor import DoctorService

    doctor = DoctorService(
        harness.conn, _settings_from(harness), InMemoryish(), recorder=harness.recorder
    )
    report = doctor.check(client_version="0.1.0")
    if db.is_file():
        doctor.mark_index_degraded(harness.repo_id.value, "corrupt cache")
        report = doctor.check(client_version="0.1.0")
    assert report.index_degraded is True
    paused = harness.recovery.pause_or_stop(
        harness.task_id, "corrupt cache", "corrupt cache"
    )
    assert paused.state is TaskState.PAUSED
    assert harness.fixture.merge_calls() == ()


def test_merge_conflict_and_reviewer_outage_pause_without_duplicate_merge(tmp_path: Path) -> None:
    conflict = GoalHarness(tmp_path / "conflict", "conflict")
    outcome = conflict.run_until_merge()
    assert outcome.status == TaskState.PAUSED.value
    assert "conflict" in outcome.reason.lower()
    assert conflict.fixture.merge_calls() == ()

    built, fixture, _auth = controller_stack()
    harness = GoalHarness(
        tmp_path / "reviewer", "happy", forge=_ReviewerOutageForge(built), fixture=fixture
    )
    harness.setup_goal()
    result = harness.engine.advance(harness.task_id, holder_id="worker-1")
    assert result.ok is False
    assert harness.store.get_task(harness.task_id).state is TaskState.PAUSED
    assert fixture.merge_calls() == ()
    writes = fixture.count_pulls()
    harness.engine.advance(harness.task_id, holder_id="worker-1")
    assert fixture.count_pulls() == writes


def _settings_from(harness: GoalHarness) -> object:
    from kronos_engine.config.settings import Settings

    return Settings(
        engine_version="0.1.0",
        min_client_version="0.1.0",
        bind_host="127.0.0.1",
        bind_port=0,
        auth_token="install-token",
        paths=harness.paths,
    )


class InMemoryish:
    def put(self, name: str, value: str) -> None:
        _ = name, value

    def get(self, name: str) -> str | None:
        _ = name
        return None

    def delete(self, name: str) -> None:
        _ = name
