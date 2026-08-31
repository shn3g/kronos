# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evidence-gated promotion: propose is not activate; harm rolls skills back."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.skill_fixtures import (
    IMMUTABLE_USEFUL,
    sample_lessons_yaml,
    useful_pack,
)

from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.memory.promotion import (
    PromotionBlocked,
    PromotionConfig,
    activate_promoted,
    consider_promotion,
    record_outcome,
)
from kronos_engine.memory.records import MemoryRejected, MemoryStatus
from kronos_engine.ports.embedding import EmbeddingPort
from kronos_engine.skills.catalog import HumanApprovalRequired, SkillCatalog
from kronos_engine.skills.quarantine import FixtureSkillSource
from kronos_engine.state.database import Database

REPO_SKILLS = Path(__file__).resolve().parents[3] / "skills"
SHA_A = "1" * 40
SHA_B = "2" * 40
SHA_C = "3" * 40
SHA_D = "4" * 40


class _BagEmbedding:
    def available(self, kind: str) -> bool:
        return kind == "document"

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        _ = kind
        vocab = ("timestamp", "timezone", "utc", "contrast", "label", "form")
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            vectors.append([1.0 if token in lowered else 0.0 for token in vocab])
        return vectors


def _settings(tmp_path: Path) -> Settings:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    return Settings(
        engine_version="0.1.0",
        min_client_version="0.1.0",
        bind_host="127.0.0.1",
        bind_port=0,
        auth_token="install-token",
        paths=paths,
    )


def _catalog(
    tmp_path: Path,
    packs: dict[tuple[str, str], Path],
    embeddings: EmbeddingPort | None = None,
) -> SkillCatalog:
    db = Database(tmp_path / "kronos.sqlite3")
    conn = db.connect()
    return SkillCatalog(
        conn,
        skills_root=tmp_path / "library",
        store_dir=tmp_path / "skill-store",
        source=FixtureSkillSource(packs),
        embeddings=embeddings,
    )


def _approve_repo_skill(catalog: SkillCatalog, locator: str, revision: str) -> str:
    installed = catalog.import_pack(locator, revision, scope="repo")
    catalog.evaluate(installed.id)
    catalog.approve(installed.id, human=True)
    return installed.id


def _grant_helpful(catalog: SkillCatalog, skill_id: str, shas: tuple[str, ...]) -> None:
    for sha in shas:
        record_outcome(
            catalog,
            skill_id=skill_id,
            source_sha=sha,
            outcome="helpful",
            text="Independent helpful run.",
            confidence=0.8,
        )


def _ready_repo_skill(catalog: SkillCatalog, locator: str, revision: str) -> str:
    skill_id = _approve_repo_skill(catalog, locator, revision)
    _grant_helpful(catalog, skill_id, (SHA_A, SHA_B, SHA_C))
    catalog.activate(skill_id)
    return skill_id


def test_useful_skill_passes_regression_then_stays_proposed_until_activate(
    tmp_path: Path,
) -> None:
    packs = {("fixture://useful", IMMUTABLE_USEFUL): useful_pack(tmp_path / "useful")}
    catalog = _catalog(tmp_path, packs)
    skill_id = _approve_repo_skill(catalog, "fixture://useful", IMMUTABLE_USEFUL)
    assert catalog.get(skill_id).status == "approved"
    config = PromotionConfig(min_independent_helpful=3)
    first = record_outcome(
        catalog,
        skill_id=skill_id,
        source_sha=SHA_A,
        outcome="helpful",
        text="Failing test caught the multiply regression.",
        confidence=0.8,
    )
    assert first.status is MemoryStatus.proposed
    record_outcome(
        catalog,
        skill_id=skill_id,
        source_sha=SHA_A,
        outcome="helpful",
        text="Same commit does not count twice.",
        confidence=0.8,
    )
    record_outcome(
        catalog,
        skill_id=skill_id,
        source_sha=SHA_B,
        outcome="helpful",
        text="Second independent SHA still not enough.",
        confidence=0.7,
    )
    early = consider_promotion(catalog, skill_id, config)
    assert early.eligible is False
    assert early.activated is False
    record_outcome(
        catalog,
        skill_id=skill_id,
        source_sha=SHA_C,
        outcome="helpful",
        text="Third independent SHA meets the configured bar.",
        confidence=0.9,
    )
    decision = consider_promotion(catalog, skill_id, config)
    assert decision.eligible is True
    assert decision.activated is False
    assert decision.needs_human is False
    procedural = catalog.procedural.for_skill(skill_id)
    assert procedural.status is MemoryStatus.proposed
    assert catalog.get(skill_id).status == "approved"
    activated = activate_promoted(catalog, skill_id)
    assert activated.status is MemoryStatus.active
    assert catalog.get(skill_id).status == "approved"
    live = catalog.activate(skill_id)
    assert live.status == "active"


def test_harmful_outcome_disables_and_rolls_back(tmp_path: Path) -> None:
    packs = {("fixture://useful", IMMUTABLE_USEFUL): useful_pack(tmp_path / "useful")}
    catalog = _catalog(tmp_path, packs)
    skill_id = _ready_repo_skill(catalog, "fixture://useful", IMMUTABLE_USEFUL)
    for sha in (SHA_A, SHA_B, SHA_C):
        record_outcome(
            catalog,
            skill_id=skill_id,
            source_sha=sha,
            outcome="helpful",
            text="Independent helpful run.",
            confidence=0.7,
        )
    activate_promoted(catalog, skill_id)
    harmed = record_outcome(
        catalog,
        skill_id=skill_id,
        source_sha=SHA_D,
        outcome="harmful",
        text="The skill caused a revert on this SHA.",
        confidence=0.95,
    )
    assert harmed.status is MemoryStatus.rolled_back
    skill = catalog.get(skill_id)
    assert skill.status in {"disabled", "rolled_back"}
    blocked = consider_promotion(catalog, skill_id, PromotionConfig(min_independent_helpful=3))
    assert blocked.eligible is False
    assert blocked.activated is False
    with pytest.raises(Exception, match="harm|rollback|disabled"):
        activate_promoted(catalog, skill_id)


def test_core_skill_changes_need_human_approval(tmp_path: Path) -> None:
    catalog = SkillCatalog(
        Database(tmp_path / "kronos.sqlite3").connect(),
        skills_root=REPO_SKILLS,
        store_dir=tmp_path / "skill-store",
        source=FixtureSkillSource({}),
    )
    core = catalog.load_core()
    tdd = next(item for item in core if item.name == "tdd")
    assert tdd.status == "active"
    assert tdd.scope == "core"
    with pytest.raises(HumanApprovalRequired):
        catalog.approve(tdd.id, human=False)
    with pytest.raises(HumanApprovalRequired):
        record = catalog.procedural.propose(
            text="Tighten TDD core guidance.",
            source_sha=SHA_A,
            skill_id=tdd.id,
            confidence=0.6,
        )
        activate_promoted(catalog, tdd.id, record_id=record.id)


def test_prior_lessons_import_as_disabled_candidates(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, {})
    imported = catalog.procedural.import_lessons(sample_lessons_yaml())
    assert len(imported) == 2
    assert {item.status for item in imported} == {MemoryStatus.disabled_candidate}
    assert all(item.kind == "procedural" for item in imported)
    assert all(item.source_sha for item in imported)
    for item in imported:
        decision = consider_promotion(catalog, item.skill_id or item.id, PromotionConfig())
        assert decision.eligible is False
        assert decision.activated is False
        with pytest.raises(Exception, match="disabled|candidate|activate"):
            activate_promoted(catalog, item.skill_id or item.id, record_id=item.id)
    assert catalog.retrieve("venue timezone") == ()


def test_memory_rejects_secrets_and_hidden_chain_of_thought(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, {})
    with pytest.raises(MemoryRejected, match="secret"):
        catalog.episodic.record(
            text="Leaked token ghp_exampletokenvalue123",
            source_sha=SHA_A,
            outcome="helpful",
            confidence=0.4,
        )
    with pytest.raises(MemoryRejected, match="chain|thinking|cot"):
        catalog.episodic.record(
            text="<thinking>hidden plan for the worker</thinking>",
            source_sha=SHA_B,
            outcome="neutral",
            confidence=0.2,
        )
    stored = catalog.episodic.record(
        text="The reproduce test failed until the fence token was checked.",
        source_sha=SHA_C,
        outcome="helpful",
        confidence=0.6,
        run_id="run_1",
        task_id="task_1",
    )
    assert stored.kind == "episodic"
    assert stored.source_sha == SHA_C
    assert 0.0 <= stored.confidence <= 1.0
    assert "<thinking>" not in stored.text


def test_retrieval_uses_text_and_has_no_booking_or_a11y_boosts(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, {}, embeddings=_BagEmbedding())
    catalog.procedural.import_lessons(sample_lessons_yaml())
    utc = catalog.procedural.propose(
        text="Store timestamps in UTC and convert at the edge.",
        source_sha=SHA_A,
        confidence=0.7,
    )
    catalog.procedural.save(replace(utc, status=MemoryStatus.active))
    hits = catalog.retrieve("timestamp timezone UTC conversion", limit=5)
    assert any(item.id == utc.id for item in hits)
    booking_hits = catalog.retrieve("booking widget checkout", limit=5)
    assert all("wcag" not in item.text.lower() for item in booking_hits)
    assert all("contrast" not in item.text.lower() for item in booking_hits)


@pytest.mark.asyncio
async def test_skills_and_memory_http_surfaces(tmp_path: Path) -> None:
    packs = {("fixture://useful", IMMUTABLE_USEFUL): useful_pack(tmp_path / "useful")}
    settings = _settings(tmp_path)
    database = Database(settings.paths.database)
    app = create_app(
        settings,
        database,
        skills_root=tmp_path / "library",
        skill_source=FixtureSkillSource(packs),
    )
    headers = {"Authorization": "Bearer install-token"}
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    ) as http:
        listed = await http.get("/skills", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["skills"] == []
        imported = await http.post(
            "/skills/import",
            headers=headers,
            json={"locator": "fixture://useful", "revision": IMMUTABLE_USEFUL, "scope": "repo"},
        )
        assert imported.status_code == 200
        skill_id = imported.json()["id"]
        assert imported.json()["status"] == "quarantined"
        evaluated = await http.post(f"/skills/{skill_id}/evaluate", headers=headers)
        assert evaluated.status_code == 200
        assert evaluated.json()["evaluation"]["passed"] is True
        approved = await http.post(
            f"/skills/{skill_id}/approve", headers=headers, json={"human": True}
        )
        assert approved.status_code == 200
        blocked = await http.post(f"/skills/{skill_id}/activate", headers=headers)
        assert blocked.status_code == 400
        conn = database.connect()
        catalog = SkillCatalog(
            conn,
            skills_root=tmp_path / "library",
            store_dir=settings.paths.cache / "skills",
            source=FixtureSkillSource(packs),
        )
        _grant_helpful(catalog, skill_id, (SHA_A, SHA_B, SHA_C))
        activated = await http.post(f"/skills/{skill_id}/activate", headers=headers)
        assert activated.status_code == 200
        assert activated.json()["status"] == "active"
        routed = await http.post(
            "/skills/route",
            headers=headers,
            json={"query": "failing test multiply", "budget_tokens": 80},
        )
        assert routed.status_code == 200
        names = [item["name"] for item in routed.json()["summaries"]]
        assert "useful-tdd" in names
        assert all(item.get("body", "") == "" for item in routed.json()["summaries"])
        lessons = await http.post(
            "/memory/import-lessons",
            headers=headers,
            json={"yaml": sample_lessons_yaml()},
        )
        assert lessons.status_code == 200
        records = lessons.json()["records"]
        assert records
        assert all(item["status"] == "disabled_candidate" for item in records)
        memory = await http.get("/memory", headers=headers)
        assert memory.status_code == 200
        assert memory.json()["records"]
        promoted = await http.post(
            f"/skills/{skill_id}/promote", headers=headers, json={"human": True}
        )
        assert promoted.status_code == 200
        assert promoted.json()["status"] == "active"


def test_evaluate_on_active_core_keeps_status(tmp_path: Path) -> None:
    catalog = SkillCatalog(
        Database(tmp_path / "kronos.sqlite3").connect(),
        skills_root=REPO_SKILLS,
        store_dir=tmp_path / "skill-store",
        source=FixtureSkillSource({}),
    )
    core = catalog.load_core()
    tdd = next(item for item in core if item.name == "tdd")
    assert tdd.status == "active"
    evaluated = catalog.evaluate(tdd.id)
    assert evaluated.status == "active"


def test_repo_activate_without_evidence_raises(tmp_path: Path) -> None:
    packs = {("fixture://useful", IMMUTABLE_USEFUL): useful_pack(tmp_path / "useful")}
    catalog = _catalog(tmp_path, packs)
    skill_id = _approve_repo_skill(catalog, "fixture://useful", IMMUTABLE_USEFUL)
    with pytest.raises(PromotionBlocked, match="evidence"):
        catalog.activate(skill_id)
    assert catalog.get(skill_id).status == "approved"


def test_execute_routes_summaries_and_records_outcome(tmp_path: Path) -> None:
    from tests.e2e.test_goal_to_integration_pr import GoalHarness, ScriptedExecutor
    from tests.support.skill_fixtures import write_skill_pack

    from kronos_engine.adapters.embeddings.local import LocalEmbeddingAdapter
    from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
    from kronos_engine.application.dispatch import DispatchService
    from kronos_engine.indexing.service import IndexingService

    class _Capture(ScriptedExecutor):
        def __init__(self) -> None:
            super().__init__("happy")
            self.last = None

        def run(self, request, sandbox):  # type: ignore[no-untyped-def]
            self.last = request
            return super().run(request, sandbox)

    capture = _Capture()
    harness = GoalHarness(tmp_path, "happy", executor=capture)
    harness.setup_goal()
    revision = "e" * 40
    packs = {
        ("fixture://add", revision): write_skill_pack(
            tmp_path / "add-fix",
            name="add-fix",
            description="Fix add in pkg math with a failing test.",
            body="# Add\n\nWrite a failing test before implementation.\n",
            scope="community",
            capabilities=("tdd",),
            permissions=("worktree_read",),
            regression={
                "verification": ["failing test before implementation"],
                "forbidden": ["rewrite backend tests"],
            },
        )
    }
    catalog = SkillCatalog(
        harness.conn,
        skills_root=tmp_path / "library",
        store_dir=tmp_path / "skill-store",
        source=FixtureSkillSource(packs),
        embeddings=LocalEmbeddingAdapter(harness.paths.cache / "models"),
    )
    installed = catalog.import_pack("fixture://add", revision, scope="community")
    catalog.evaluate(installed.id)
    catalog.approve(installed.id, human=True)
    catalog.activate(installed.id)
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
    summaries = capture.last.context.skill_summaries
    assert any("add-fix" in item for item in summaries)
    assert all("Write a failing test before implementation" not in item for item in summaries)
    assert "GH_TOKEN" not in capture.last.worker_env
    assert "KRONOS_REVIEWER" not in capture.last.worker_env
    recorded = catalog.procedural.for_skill(installed.id)
    assert recorded.source_sha
    assert recorded.outcome == "helpful"
    assert recorded.helpful >= 1
    assert recorded.harmful == 0


def test_execute_failure_leaves_core_tdd_active(tmp_path: Path) -> None:
    from tests.e2e.test_goal_to_integration_pr import GoalHarness

    from kronos_engine.adapters.embeddings.local import LocalEmbeddingAdapter
    from kronos_engine.adapters.sandboxes.process_jail import ProcessJailSandbox
    from kronos_engine.application.dispatch import DispatchService
    from kronos_engine.indexing.service import IndexingService

    harness = GoalHarness(tmp_path, "model_outage")
    harness.setup_goal()
    catalog = SkillCatalog(
        harness.conn,
        skills_root=REPO_SKILLS,
        store_dir=tmp_path / "skill-store",
        source=FixtureSkillSource({}),
        embeddings=LocalEmbeddingAdapter(harness.paths.cache / "models"),
    )
    core = catalog.load_core()
    tdd = next(item for item in core if item.name == "tdd")
    assert tdd.status == "active"
    harness.dispatch = DispatchService(
        harness.store,
        harness.repos,
        harness.leases,
        harness.recorder,
        IndexingService(harness.paths),
        harness.executor,
        lambda worktree: ProcessJailSandbox(worktree),
        harness.paths.cache,
        clock=lambda: harness.now,
        skills=catalog,
    )
    claimed = harness.dispatch.claim(harness.task_id, dry_run=False, holder_id="worker-1")
    assert claimed.ok is True
    executed = harness.dispatch.execute(claimed, phase="red")
    assert executed.ok is False
    assert catalog.get(tdd.id).status == "active"
