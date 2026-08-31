# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eight bounded outcomes from a goal to an integration PR. No live GitHub."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from tests.support.git_fixtures import init_git_repo
from tests.support.github_fixture import controller_stack

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
from kronos_engine.application.dispatch import DispatchService
from kronos_engine.application.goals import GoalService
from kronos_engine.application.merge import MergeService
from kronos_engine.application.planning import PlanningService
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.recovery import RecoveryService
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.application.verification import VerificationService
from kronos_engine.config.paths import resolve_paths
from kronos_engine.domain.attestations import ATTESTATION_SCHEMA_VERSION
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.domain.goals import GoalSource, GoalSpec, GoalState
from kronos_engine.domain.policy import parse_policy, policy_to_dict
from kronos_engine.domain.tasks import TaskState
from kronos_engine.domain.workflow import (
    CLAIM_STEPS,
    ClaimRequiresTaskId,
    ScheduledSpawnForbidden,
)
from kronos_engine.indexing.service import IndexingService
from kronos_engine.ports.executor import ExecutorRequest, ExecutorResult, UsageMetadata
from kronos_engine.ports.forge import ForgeError
from kronos_engine.ports.sandbox import Sandbox
from kronos_engine.state.database import Database
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.leases import SqliteLeases
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry
from kronos_engine.state.scheduler import GoalScheduler

Script = Literal[
    "happy",
    "failing_test",
    "no_test",
    "ci_fail",
    "model_outage",
    "restart",
    "conflict",
    "budget_exhaustion",
]

ATTESTATION_KEY = b"kronos-test-attestation-key"
REVIEWER_APP_ID = 1002
CONTROLLER_APP_ID = 1001

POLICY_YAML = """schema_version: 2
branches:
  integration: integration
  protected: main
commands:
  setup: []
  test:
    - pytest
    - -q
  lint: []
  build: []
autonomy:
  freeze: false
  invent_issues: false
  refill_enabled: false
paths:
  locked_prefixes: []
risk:
  floor: low
budgets:
  max_attempts_per_issue: 3
  max_dispatches_per_day: 12
  breaker_failure_limit: 4
  dry_run_meters: false
wip:
  ready: 2
  running: 3
executor:
  profile: standard
  sandbox: default
indexing:
  enabled: true
  exclude_prefixes:
    - node_modules/
  max_file_bytes: 1048576
"""

POLICY_OVERRIDE = {
    "autonomy": {"freeze": False, "invent_issues": False, "refill_enabled": False},
    "branches": {"integration": "integration", "protected": "main"},
    "commands": {"setup": [], "test": ["pytest", "-q"], "lint": [], "build": []},
    "budgets": {
        "max_attempts_per_issue": 3,
        "max_dispatches_per_day": 12,
        "breaker_failure_limit": 4,
        "dry_run_meters": False,
    },
}


def _sign(payload: Mapping[str, object]) -> str:
    body = {key: value for key, value in payload.items() if key != "signature"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(ATTESTATION_KEY, canonical, hashlib.sha256).hexdigest()


def _attestation_json(*, head_sha: str, base_sha: str) -> str:
    payload: dict[str, object] = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "run_id": "run-e2e",
        "head_sha": head_sha,
        "base_sha": base_sha,
        "check_name": KRONOS_REVIEW_CHECK_NAME,
        "reviewer_app_id": REVIEWER_APP_ID,
        "conclusion": "success",
        "policy_source": "base",
        "commands": [{"argv": ["pytest", "-q"], "exit_code": 0, "sandbox_fresh": True}],
        "risk": "low",
    }
    payload["signature"] = _sign(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class ScriptedExecutor:
    def __init__(self, script: Script) -> None:
        self.script = script
        self.runs = 0

    def run(self, request: ExecutorRequest, sandbox: Sandbox) -> ExecutorResult:
        self.runs += 1
        if request.capabilities.autonomous_merge:
            sandbox.authorize_autonomous_merge()
        sandbox.enforce_capabilities(
            network=request.capabilities.network,
            secrets=request.capabilities.secrets,
            root=request.capabilities.root,
        )
        sandbox.worker_environment(request.worker_env)
        if self.script == "model_outage":
            return ExecutorResult(
                status="failed",
                artifacts=(),
                usage=_usage(self.runs),
                error="model outage: planner/coder unavailable",
            )
        if self.script == "no_test":
            sandbox.write_text("pkg/math.py", "def add(a, b):\n    return a + b\n")
            return ExecutorResult(
                status="succeeded",
                artifacts=("pkg/math.py",),
                usage=_usage(self.runs),
            )
        sandbox.write_text(
            "tests/test_repro.py",
            "from pkg.math import add\n\ndef test_add():\n    assert add(1, 1) == 2\n",
        )
        sandbox.write_text("pkg/math.py", "def add(a, b):\n    return a + b\n")
        return ExecutorResult(
            status="succeeded",
            artifacts=("tests/test_repro.py", "pkg/math.py"),
            usage=_usage(self.runs),
        )


class ScriptedPlanner:
    def plan(self, goal: object) -> dict[str, object]:
        _ = goal
        return {
            "tasks": [
                {
                    "id": "task_add",
                    "title": "fix add",
                    "kind": "implementation",
                    "depends_on": [],
                    "evidence": [{"path": "pkg/math.py", "line": 1}],
                    "size": "S",
                    "baseline_size": "XS",
                    "risk": "low",
                    "scope_paths": ["pkg/math.py"],
                }
            ]
        }


class ScriptedGates:
    def __init__(self, script: Script) -> None:
        self.script = script

    def run(self, worktree: Path, commands: tuple[tuple[str, ...], ...]) -> list[dict[str, object]]:
        _ = worktree
        _ = commands
        passed = self.script not in {"failing_test"}
        return [{"name": "test", "passed": passed, "output": "ok" if passed else "assert False"}]


class _ConflictForge:
    def __init__(self, inner: object) -> None:
        self._inner = inner

    def merge_pull(self, number: int, *, sha: str, dest: str | None = None) -> None:
        _ = number
        _ = sha
        _ = dest
        raise ForgeError("merge conflict: pull is not mergeable")

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


@dataclass
class Outcome:
    status: str
    reason: str
    goal_id: str
    task_id: str
    pr_url: str | None
    pr_base: str | None
    events: tuple[str, ...]
    claim_steps: tuple[str, ...]
    budget_attempts: int


class GoalHarness:
    def __init__(
        self,
        tmp_path: Path,
        script: Script,
        *,
        db: Database | None = None,
        forge: object | None = None,
        fixture: object | None = None,
        executor: ScriptedExecutor | None = None,
        reuse_repo: bool = False,
    ) -> None:
        self.tmp_path = tmp_path
        self.script = script
        self.paths = resolve_paths(
            {
                "KRONOS_DATA_HOME": str(tmp_path / "data"),
                "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
                "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
                "KRONOS_LOG_HOME": str(tmp_path / "logs"),
            }
        )
        self.db = db or Database(self.paths.database)
        if forge is None or fixture is None:
            built, fixture_obj, _auth = controller_stack()
            self.forge = built if forge is None else forge
            self.fixture = fixture_obj
        else:
            self.forge = forge
            self.fixture = fixture
        if script == "conflict":
            self.forge = _ConflictForge(self.forge)
        self.executor = executor or ScriptedExecutor(script)
        self.now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
        enrolled = tmp_path / "enrolled"
        if reuse_repo and enrolled.exists():
            self.repo_root = enrolled
        else:
            self.repo_root = init_git_repo(
                enrolled,
                files={
                    "pkg/math.py": "def add(a, b):\n    return a\n",
                    "pkg/__init__.py": "",
                    "tests/__init__.py": "",
                },
                origin="https://github.com/acme/app.git",
                branch="main",
            )
        self._wire()

    def _wire(self) -> None:
        conn = self.db.connect()
        self.conn = conn
        self.store = SqliteGoalStore(conn)
        self.events = SqliteEventStore(conn)
        self.outbox = SqliteOutbox(conn)
        self.recorder = Recorder(conn, self.events, self.outbox)
        self.leases = SqliteLeases(conn)
        registry = SqliteRepositoryRegistry(conn)
        self.repos = RepositoryService(
            registry,
            self.paths,
            FilesystemGitInspector(),
            ManifestStackDetector(),
            CacheRuntimeLayout(),
            indexer=IndexingService(self.paths),
        )
        merge_forge = self.forge
        self.merge = MergeService(
            merge_forge,  # type: ignore[arg-type]
            attestation_key=ATTESTATION_KEY,
            expected_reviewer_app_id=REVIEWER_APP_ID,
            expected_controller_app_id=CONTROLLER_APP_ID,
        )
        self.goals = GoalService(self.store, self.repos, self.recorder)
        self.planning = PlanningService(self.store, self.repos, self.recorder, ScriptedPlanner())
        self.dispatch = DispatchService(
            self.store,
            self.repos,
            self.leases,
            self.recorder,
            IndexingService(self.paths),
            self.executor,
            lambda worktree: ProcessJailSandbox(worktree),
            self.paths.cache,
            clock=lambda: self.now,
        )
        self.verification = VerificationService(
            self.store,
            self.repos,
            self.recorder,
            self.forge,  # type: ignore[arg-type]
            ScriptedGates(self.script),
            clock=lambda: self.now,
        )
        self.recovery = RecoveryService(self.store, self.recorder)
        self.scheduler = GoalScheduler(self.store, self.goals)

    def setup_goal(self) -> None:
        overrides = dict(POLICY_OVERRIDE)
        if self.script == "budget_exhaustion":
            overrides = {
                **overrides,
                "budgets": {
                    **POLICY_OVERRIDE["budgets"],
                    "max_attempts_per_issue": 1,
                },
            }
        record = self.repos.enrol(str(self.repo_root), overrides)
        self.repo_id = record.id
        IndexingService(self.paths).rebuild(record.id.value, self.repo_root, record.policy)
        self.fixture.seed_contents(  # type: ignore[union-attr]
            self.fixture.integration_sha,  # type: ignore[union-attr]
            ".kronos/config.yaml",
            POLICY_YAML,
        )
        self.fixture.seed_ruleset(  # type: ignore[union-attr]
            {
                "name": "kronos-integration",
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "strict_required_status_checks_policy": True,
                            "required_status_checks": [
                                {
                                    "context": KRONOS_REVIEW_CHECK_NAME,
                                    "integration_id": REVIEWER_APP_ID,
                                }
                            ],
                        },
                    }
                ],
            }
        )
        goal = self.goals.create(
            GoalSpec(
                repository_id=record.id,
                title="Fix add",
                success_criteria="add(1, 1) == 2",
                non_goals="do not rewrite packaging",
                risk_ceiling="medium",
                source=GoalSource.DESKTOP,
            )
        )
        self.goal = goal
        graph = self.planning.plan(goal.id)
        self.task_id = graph.nodes[0].id

    def set_freeze(self, freeze: bool) -> None:
        record = self.repos.get(self.repo_id)
        payload = policy_to_dict(record.policy)
        autonomy = dict(payload["autonomy"])  # type: ignore[arg-type]
        autonomy["freeze"] = freeze
        payload["autonomy"] = autonomy
        updated = replace(record, policy=parse_policy(payload))
        SqliteRepositoryRegistry(self.conn).save(updated)

    def reconnect(self) -> GoalHarness:
        clone = GoalHarness(
            self.tmp_path,
            self.script,
            db=self.db,
            forge=self.forge if self.script != "conflict" else self.forge._inner,  # type: ignore[attr-defined]
            fixture=self.fixture,
            executor=self.executor,
            reuse_repo=True,
        )
        clone.repo_id = self.repo_id
        clone.goal = self.store.get_goal(self.goal.id)
        clone.task_id = self.task_id
        return clone

    def run_until_merge(self) -> Outcome:
        self.setup_goal()
        if self.script == "restart":
            self._advance(stop_after="pr")
            restarted = self.reconnect()
            restarted._simulate_reviewer()
            return restarted._merge_or_recover()
        claimed = self.dispatch.claim(self.task_id, dry_run=False, holder_id="worker-1")
        if self.script == "budget_exhaustion":
            self.dispatch.execute(claimed)
            self.recovery.pause_task(
                self.task_id,
                reason="executor failed on first attempt",
                evidence="model returned failed",
            )
            second = self.dispatch.claim(self.task_id, dry_run=False, holder_id="worker-1")
            if not second.ok:
                paused = self.recovery.pause_task(
                    self.task_id,
                    reason=second.reason,
                    evidence="attempt cap reached",
                )
                return self._outcome(
                    paused.state.value,
                    paused.stop_reason or second.reason,
                    claimed.steps,
                )
        executed = self.dispatch.execute(claimed)
        verified = self.verification.accept(self.task_id, executed)
        if not verified.ok:
            paused = self.recovery.pause_or_stop(self.task_id, verified.reason, verified.evidence)
            return self._outcome(
                paused.state.value,
                paused.stop_reason or verified.reason,
                claimed.steps,
            )
        pull = self.verification.open_integration_pr(self.task_id)
        if self.script == "ci_fail":
            self._simulate_ci_failure(pull.number, pull.head_sha)
        else:
            self._simulate_reviewer()
        merged = self.verification.merge_if_eligible(self.task_id, self.merge)
        if not merged.ok:
            paused = self.recovery.pause_task(
                self.task_id, reason=merged.reason, evidence=merged.reason
            )
            return self._outcome(
                paused.state.value,
                paused.stop_reason or merged.reason,
                claimed.steps,
            )
        return self._outcome(TaskState.MERGED.value, merged.reason, claimed.steps)

    def _advance(self, *, stop_after: str) -> Outcome:
        claimed = self.dispatch.claim(self.task_id, dry_run=False, holder_id="worker-1")
        executed = self.dispatch.execute(claimed)
        verified = self.verification.accept(self.task_id, executed)
        assert verified.ok
        pull = self.verification.open_integration_pr(self.task_id)
        _ = pull
        _ = stop_after
        return self._outcome("awaiting_review", "draft PR opened", claimed.steps)

    def _merge_or_recover(self) -> Outcome:
        merged = self.verification.merge_if_eligible(self.task_id, self.merge)
        if not merged.ok:
            paused = self.recovery.pause_task(
                self.task_id, reason=merged.reason, evidence=merged.reason
            )
            return self._outcome(paused.state.value, paused.stop_reason or merged.reason, ())
        return self._outcome(TaskState.MERGED.value, merged.reason, ())

    def _simulate_reviewer(self) -> None:
        task = self.store.get_task(self.task_id)
        assert task.pr_number is not None
        pull = next(item for item in self.fixture.pulls() if item["number"] == task.pr_number)
        head_sha = str(pull["head"]["sha"])
        base_sha = str(pull["base"]["sha"])
        self.fixture.seed_check_run(
            name=KRONOS_REVIEW_CHECK_NAME,
            head_sha=head_sha,
            app_id=REVIEWER_APP_ID,
            output={
                "title": KRONOS_REVIEW_CHECK_NAME,
                "summary": "independent review passed",
                "text": _attestation_json(head_sha=head_sha, base_sha=base_sha),
            },
        )

    def _simulate_ci_failure(self, number: int, head_sha: str) -> None:
        _ = number
        self.fixture.seed_check_run(
            name="pytest",
            head_sha=head_sha,
            app_id=None,
            conclusion="failure",
            posted_by="worker",
        )

    def _outcome(self, status: str, reason: str, steps: tuple[str, ...]) -> Outcome:
        task = self.store.get_task(self.task_id)
        events = tuple(item.type for item in self.events.list_after(0))
        attempts = self.store.task_attempts(self.task_id)
        return Outcome(
            status=status,
            reason=reason,
            goal_id=self.goal.id.value,
            task_id=self.task_id.value,
            pr_url=task.pr_url,
            pr_base=task.pr_base,
            events=events,
            claim_steps=steps,
            budget_attempts=attempts,
        )


def _usage(attempts: int) -> UsageMetadata:
    return UsageMetadata(
        attempts=attempts,
        tokens=0,
        elapsed_seconds=0.0,
        cost=0.0,
        model_id="scripted",
        executor_id="scripted",
    )


def test_happy_path_reaches_eligible_integration_merge(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.MERGED.value
    assert outcome.reason
    assert outcome.pr_url
    assert outcome.pr_base == "integration"
    assert harness.fixture.merge_calls()
    assert "goal.created" in outcome.events
    assert "task.transitioned" in outcome.events
    assert outcome.claim_steps == CLAIM_STEPS
    goal = harness.store.get_goal(harness.goal.id)
    assert goal.state is GoalState.COMPLETED


def test_failing_test_pauses_with_actionable_evidence(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "failing_test")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.PAUSED.value
    assert "test" in outcome.reason.lower()
    assert harness.fixture.merge_calls() == ()
    assert outcome.reason


def test_no_test_is_a_stop_not_a_merge(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "no_test")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.STOPPED.value
    assert "no-test" in outcome.reason.lower() or "reproduction" in outcome.reason.lower()
    assert harness.fixture.merge_calls() == ()
    assert outcome.pr_url is None


def test_ci_fail_pauses_without_merge(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "ci_fail")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.PAUSED.value
    assert outcome.reason
    assert harness.fixture.merge_calls() == ()
    assert outcome.pr_url


def test_model_outage_pauses_with_actionable_evidence(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "model_outage")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.PAUSED.value
    assert "outage" in outcome.reason.lower()
    assert harness.fixture.merge_calls() == ()


def test_restart_resumes_without_duplicate_external_writes(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "restart")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.MERGED.value
    assert harness.fixture.count_pulls() == 1
    assert harness.fixture.merge_calls()


def test_conflict_pauses_with_explainable_outcome(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "conflict")
    outcome = harness.run_until_merge()
    assert outcome.status == TaskState.PAUSED.value
    assert "conflict" in outcome.reason.lower()
    assert harness.fixture.merge_calls() == ()


def test_budget_exhaustion_pauses_after_attempt_limit(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "budget_exhaustion")
    outcome = harness.run_until_merge()
    assert outcome.status in {TaskState.PAUSED.value, TaskState.STOPPED.value}
    assert "attempt" in outcome.reason.lower() or "budget" in outcome.reason.lower()
    assert harness.fixture.merge_calls() == ()
    assert outcome.budget_attempts >= 1


def test_freeze_blocks_before_budget_and_dry_run_does_not_consume(tmp_path: Path) -> None:
    harness = GoalHarness(tmp_path, "happy")
    harness.setup_goal()
    harness.set_freeze(True)
    refused = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert refused.ok is False
    assert refused.failed_step == "freeze"
    assert harness.store.task_attempts(harness.task_id) == 0
    harness.set_freeze(False)
    dry = harness.dispatch.claim(harness.task_id, dry_run=True, holder_id="worker-1")
    assert dry.ok is True
    assert dry.budget_consumed is False
    assert harness.store.task_attempts(harness.task_id) == 0
    assert dry.steps[:3] == ("freeze", "budget", "evidence")
    with pytest.raises(ClaimRequiresTaskId):
        harness.dispatch.claim(None, dry_run=True, holder_id="worker-1")
    with pytest.raises(ScheduledSpawnForbidden):
        harness.scheduler.spawn(task_id=None)
