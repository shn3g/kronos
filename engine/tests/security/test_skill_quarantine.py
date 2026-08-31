# SPDX-License-Identifier: AGPL-3.0-or-later
"""Imported skills stay quarantined until evaluated; malicious packs never activate."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from tests.support.skill_fixtures import (
    IMMUTABLE_IRRELEVANT,
    IMMUTABLE_MALICIOUS,
    IMMUTABLE_USEFUL,
    irrelevant_pack,
    malicious_pack,
    useful_pack,
    write_skill_pack,
)

from kronos_engine.skills.catalog import SkillCatalog
from kronos_engine.skills.evaluation import evaluate_skill
from kronos_engine.skills.loader import load_library, load_skill_dir
from kronos_engine.skills.manifest import SkillManifestError, parse_skill_md
from kronos_engine.skills.quarantine import (
    FixtureSkillSource,
    MutableRevisionError,
    NetworkFetchForbidden,
    SkillStillQuarantined,
    is_immutable_revision,
    scan_skill_pack,
)
from kronos_engine.skills.router import route_skills
from kronos_engine.state.database import Database

REPO_SKILLS = Path(__file__).resolve().parents[3] / "skills"


def _catalog(tmp_path: Path, packs: dict[tuple[str, str], Path]) -> SkillCatalog:
    db = Database(tmp_path / "kronos.sqlite3")
    conn = db.connect()
    source = FixtureSkillSource(packs)
    return SkillCatalog(
        conn,
        skills_root=tmp_path / "library",
        store_dir=tmp_path / "skill-store",
        source=source,
    )


def test_skill_md_requires_name_description_and_capability_declarations() -> None:
    parsed = parse_skill_md(
        "---\n"
        "name: tdd\n"
        "description: Write a failing test before implementation.\n"
        "allowed-tools: Read Write\n"
        "metadata:\n"
        "  capabilities:\n"
        "    - tdd\n"
        "  permissions:\n"
        "    - worktree_write\n"
        "  scope: core\n"
        "---\n\n"
        "# TDD\n\nWrite the failing test first.\n"
    )
    assert parsed.name == "tdd"
    assert "failing test" in parsed.description
    assert parsed.capabilities == ("tdd",)
    assert parsed.permissions == ("worktree_write",)
    assert parsed.allowed_tools == ("Read", "Write")
    assert parsed.scope == "core"
    assert parsed.body.startswith("# TDD")
    assert "Write the failing test first" not in parsed.summary
    with pytest.raises(SkillManifestError, match="name"):
        parse_skill_md("---\ndescription: only desc\n---\n\nbody\n")
    with pytest.raises(SkillManifestError, match="description"):
        parse_skill_md("---\nname: x\n---\n\nbody\n")


def test_mutable_revisions_are_rejected() -> None:
    assert is_immutable_revision("a" * 40)
    assert is_immutable_revision("b" * 64)
    assert not is_immutable_revision("main")
    assert not is_immutable_revision("HEAD")
    assert not is_immutable_revision("v1.2.3")
    assert not is_immutable_revision("latest")
    source = FixtureSkillSource({})
    with pytest.raises(MutableRevisionError):
        source.fetch("fixture://useful", "main")


def test_scan_does_not_execute_untrusted_scripts(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    pack = malicious_pack(tmp_path / "evil", marker)
    scan = scan_skill_pack(pack)
    assert scan.executed_scripts is False
    assert not marker.exists()
    assert "scripts/exfil.py" in scan.scripts
    assert scan.malicious is True
    assert {item.code for item in scan.findings} >= {"network", "secrets", "path_escape"}
    assert "network" in scan.declared_permissions or "network" in scan.inferred_permissions


def test_imported_malicious_skill_stays_quarantined(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    packs = {("fixture://evil", IMMUTABLE_MALICIOUS): malicious_pack(tmp_path / "evil", marker)}
    catalog = _catalog(tmp_path, packs)
    installed = catalog.import_pack("fixture://evil", IMMUTABLE_MALICIOUS)
    assert installed.status == "quarantined"
    assert installed.scan.malicious is True
    assert not marker.exists()
    result = evaluate_skill(installed)
    assert result.passed is False
    assert result.security_passed is False
    with pytest.raises(SkillStillQuarantined):
        catalog.approve(installed.id, human=True)
    with pytest.raises(SkillStillQuarantined):
        catalog.activate(installed.id)
    again = catalog.get(installed.id)
    assert again.status == "quarantined"
    assert not marker.exists()


def test_default_source_does_not_hit_the_network(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, {})
    with pytest.raises((NetworkFetchForbidden, MutableRevisionError)):
        catalog.import_pack("https://example.invalid/skills/community", "main")
    with pytest.raises(NetworkFetchForbidden):
        catalog.import_pack("https://example.invalid/skills/community", IMMUTABLE_USEFUL)


def test_router_keeps_irrelevant_skills_out_of_context(tmp_path: Path) -> None:
    packs = {
        ("fixture://useful", IMMUTABLE_USEFUL): useful_pack(tmp_path / "useful"),
        ("fixture://css", IMMUTABLE_IRRELEVANT): irrelevant_pack(tmp_path / "css"),
    }
    catalog = _catalog(tmp_path, packs)
    useful = catalog.import_pack("fixture://useful", IMMUTABLE_USEFUL, scope="repo")
    css = catalog.import_pack("fixture://css", IMMUTABLE_IRRELEVANT, scope="community")
    catalog.evaluate(useful.id)
    catalog.approve(useful.id, human=True)
    catalog.activate(useful.id)
    catalog.evaluate(css.id)
    catalog.approve(css.id, human=True)
    catalog.activate(css.id)
    routed = route_skills(
        "write a failing test for multiply",
        catalog.list(),
        budget_tokens=80,
    )
    names = {item.name for item in routed.summaries}
    assert "useful-tdd" in names
    assert "css-animation" not in names
    assert routed.selected is None
    assert all(item.body == "" for item in routed.summaries)
    selected = route_skills(
        "write a failing test for multiply",
        catalog.list(),
        budget_tokens=400,
        selected_name="useful-tdd",
    )
    assert selected.selected is not None
    assert selected.selected.name == "useful-tdd"
    assert "failing test before implementation" in selected.selected.body
    assert all(item.name != "css-animation" for item in selected.summaries)


def test_router_respects_token_budget_and_does_not_treat_count_as_quality(
    tmp_path: Path,
) -> None:
    packs: dict[tuple[str, str], Path] = {}
    catalog = _catalog(tmp_path, packs)
    for index in range(8):
        revision = f"{index:040x}"
        locator = f"fixture://pad-{index}"
        packs[(locator, revision)] = write_skill_pack(
            tmp_path / f"pad-{index}",
            name=f"pad-{index}",
            description="Python failing test helper for small numeric functions.",
            body="# Pad\n\nWrite a failing test before implementation.\n",
            scope="repo",
            regression={
                "verification": ["failing test before implementation"],
                "forbidden": ["implement before a failing test"],
            },
        )
        installed = catalog.import_pack(locator, revision, scope="repo")
        catalog.evaluate(installed.id)
        catalog.approve(installed.id, human=True)
        catalog.activate(installed.id)
    routed = route_skills("failing test python", catalog.list(), budget_tokens=12)
    assert routed.tokens_used <= 12
    assert 1 <= len(routed.summaries) < 8
    assert routed.selected is None


def test_score_functions_have_no_query_specific_boost_tables() -> None:
    roots = [
        Path(__file__).resolve().parents[2] / "src" / "kronos_engine" / "skills",
        Path(__file__).resolve().parents[2] / "src" / "kronos_engine" / "memory",
    ]
    blobs: list[str] = []
    trees: list[ast.AST] = []
    for root in roots:
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            blobs.append(text)
            trees.append(ast.parse(text))
    combined = "\n".join(blobs).lower()
    for needle in ("booking", "a11y", "query_boost", "boost_table", "query_weights"):
        assert needle not in combined
    signature = inspect.signature(route_skills)
    assert "boost" not in signature.parameters
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [key.value for key in node.keys if isinstance(key, ast.Constant)]
                lowered = [str(key).lower() for key in keys if isinstance(key, str)]
                assert "booking" not in lowered
                assert "a11y" not in lowered
                assert not any("boost" in item for item in lowered)


def test_hermes_is_not_a_skill_runtime_default() -> None:
    skills_pkg = Path(__file__).resolve().parents[2] / "src" / "kronos_engine" / "skills"
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in skills_pkg.glob("*.py")
    ).lower()
    assert "localappdata" not in combined or "hermes" not in combined
    assert "hermes-reviewer" not in combined
    assert "%localappdata%/hermes" not in combined


def test_shipped_core_library_is_focused_and_has_regression_contracts() -> None:
    core = load_library(REPO_SKILLS / "core")
    assert 15 <= len(core) <= 25
    names = {item.name for item in core}
    expected = {
        "repository-inspection",
        "planning",
        "tdd",
        "debugging",
        "code-review",
        "security-review",
        "git-github",
        "dependency-changes",
        "migrations",
        "frontend-testing",
        "backend-testing",
        "accessibility",
        "documentation",
        "research-citations",
        "skill-regression",
    }
    assert expected <= names
    for skill in core:
        loaded = load_skill_dir(REPO_SKILLS / "core" / skill.name)
        assert loaded.name == skill.name
        contract = REPO_SKILLS / "regression" / f"{skill.name}.yaml"
        assert contract.is_file(), skill.name
        assert skill.capabilities
        assert skill.permissions
        assert skill.description
        assert skill.body
