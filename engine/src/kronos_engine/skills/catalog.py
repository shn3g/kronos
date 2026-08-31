# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installed skill catalog, quarantine, and activation."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.memory.episodic import EpisodicStore
from kronos_engine.memory.procedural import ProceduralStore, retrieve_records
from kronos_engine.memory.records import MemoryRecord
from kronos_engine.ports.embedding import EmbeddingPort
from kronos_engine.skills.evaluation import (
    RegressionContract,
    evaluate_skill,
    load_regression_contract,
)
from kronos_engine.skills.loader import load_library, load_skill_dir
from kronos_engine.skills.manifest import SkillManifest
from kronos_engine.skills.quarantine import (
    LocalOnlySkillSource,
    MutableRevisionError,
    NetworkFetchForbidden,
    ScanFinding,
    SkillScan,
    SkillSourcePort,
    SkillStillQuarantined,
    is_immutable_revision,
    scan_skill_pack,
)
from kronos_engine.skills.router import RoutedSkills, route_skills


class HumanApprovalRequired(ValueError):
    """Raised when a core or global skill change lacks a human."""


@dataclass(frozen=True, slots=True)
class InstalledSkill:
    id: str
    name: str
    revision: str
    locator: str
    status: str
    scope: str
    repository_id: str | None
    manifest: SkillManifest
    scan: SkillScan
    contract: RegressionContract | None = None
    pack_path: str | None = None


class SkillCatalog:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        skills_root: Path,
        store_dir: Path,
        source: SkillSourcePort | None = None,
        embeddings: EmbeddingPort | None = None,
    ) -> None:
        self._conn = conn
        self._skills_root = skills_root
        self._store_dir = store_dir
        self._source: SkillSourcePort = source or LocalOnlySkillSource()
        self._embeddings = embeddings
        self.episodic = EpisodicStore(conn, embeddings)
        self.procedural = ProceduralStore(conn, embeddings)
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def load_core(self) -> tuple[InstalledSkill, ...]:
        core_dir = self._skills_root / "core"
        if not core_dir.is_dir():
            return ()
        regression_root = self._skills_root / "regression"
        installed: list[InstalledSkill] = []
        for manifest in load_library(core_dir):
            pack = core_dir / manifest.name
            digest = hashlib.sha1(manifest.body.encode()).hexdigest()
            scan = scan_skill_pack(pack)
            contract = _contract_for(pack, regression_root, manifest.name)
            skill = InstalledSkill(
                id=f"skill-{manifest.name}-core",
                name=manifest.name,
                revision=digest,
                locator="bundled",
                status="active",
                scope="core",
                repository_id=None,
                manifest=manifest,
                scan=scan,
                contract=contract,
                pack_path=str(pack),
            )
            try:
                installed.append(self.get(skill.id))
            except LookupError:
                self._upsert(skill)
                installed.append(skill)
        return tuple(installed)

    def list(self) -> tuple[InstalledSkill, ...]:
        rows = self._conn.execute("SELECT * FROM skills ORDER BY name").fetchall()
        return tuple(self._from_row(row) for row in rows)

    def get(self, skill_id: str) -> InstalledSkill:
        row = self._conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if row is None:
            raise LookupError(skill_id)
        return self._from_row(row)

    def import_pack(
        self,
        locator: str,
        revision: str,
        *,
        scope: str | None = None,
        repository_id: str | None = None,
    ) -> InstalledSkill:
        if not is_immutable_revision(revision):
            raise MutableRevisionError("revision must be an immutable SHA")
        if locator.startswith("http://") or locator.startswith("https://"):
            raise NetworkFetchForbidden("community HTTP fetch is disabled")
        pack = self._source.fetch(locator, revision)
        scan = scan_skill_pack(pack)
        manifest = load_skill_dir(pack)
        chosen_scope = scope or manifest.scope
        skill_id = f"skill-{manifest.name}-{revision[:12]}"
        dest = self._store_dir / "quarantine" / skill_id
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(pack, dest)
        contract = _contract_for(dest, self._skills_root / "regression", manifest.name)
        skill = InstalledSkill(
            id=skill_id,
            name=manifest.name,
            revision=revision,
            locator=locator,
            status="quarantined",
            scope=chosen_scope,
            repository_id=repository_id,
            manifest=manifest,
            scan=scan,
            contract=contract,
            pack_path=str(dest),
        )
        self._upsert(skill)
        return skill

    def evaluate(self, skill_id: str) -> InstalledSkill:
        skill = self.get(skill_id)
        result = evaluate_skill(skill)
        if result.passed and skill.status == "quarantined":
            self._set_status(skill_id, "evaluated")
        return self.get(skill_id)

    def approve(self, skill_id: str, *, human: bool) -> InstalledSkill:
        skill = self.get(skill_id)
        if skill.scope in {"core", "global"} and not human:
            raise HumanApprovalRequired("core skill changes need a human")
        if skill.scan.malicious:
            raise SkillStillQuarantined("imported skill remains quarantined")
        result = evaluate_skill(skill)
        if not result.passed:
            raise SkillStillQuarantined("imported skill remains quarantined")
        self._set_status(skill_id, "approved")
        return self.get(skill_id)

    def activate(self, skill_id: str) -> InstalledSkill:
        skill = self.get(skill_id)
        if skill.scan.malicious or skill.status == "quarantined":
            raise SkillStillQuarantined("imported skill remains quarantined")
        if skill.status in {"disabled", "rolled_back"}:
            raise SkillStillQuarantined("imported skill remains quarantined")
        if skill.status not in {"approved", "active", "evaluated"}:
            raise SkillStillQuarantined("imported skill remains quarantined")
        if skill.status == "evaluated":
            raise SkillStillQuarantined("approval is required before activation")
        if skill.scope == "repo":
            from kronos_engine.memory.promotion import PromotionBlocked, consider_promotion

            try:
                decision = consider_promotion(self, skill_id)
            except LookupError as error:
                raise PromotionBlocked("insufficient evidence") from error
            if not decision.eligible:
                raise PromotionBlocked(decision.reason)
        self._set_status(skill_id, "active")
        return self.get(skill_id)

    def disable(self, skill_id: str, reason: str) -> InstalledSkill:
        _ = reason
        self._set_status(skill_id, "rolled_back")
        return self.get(skill_id)

    def route(
        self,
        query: str,
        *,
        budget_tokens: int,
        selected_name: str | None = None,
    ) -> RoutedSkills:
        return route_skills(
            query,
            self.list(),
            budget_tokens=budget_tokens,
            selected_name=selected_name,
        )

    def retrieve(self, query: str, *, limit: int = 5) -> tuple[MemoryRecord, ...]:
        return retrieve_records(self._conn, query, self._embeddings, limit=limit)

    def _set_status(self, skill_id: str, status: str) -> None:
        self._conn.execute("UPDATE skills SET status = ? WHERE id = ?", (status, skill_id))
        self._conn.commit()

    def _upsert(self, skill: InstalledSkill) -> None:
        payload = _skill_payload(skill)
        self._conn.execute(
            """
            INSERT INTO skills(
                id, name, revision, locator, status, scope, repository_id,
                manifest_json, body, scan_json, contract_json, pack_path, installed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                revision = excluded.revision,
                locator = excluded.locator,
                status = excluded.status,
                scope = excluded.scope,
                repository_id = excluded.repository_id,
                manifest_json = excluded.manifest_json,
                body = excluded.body,
                scan_json = excluded.scan_json,
                contract_json = excluded.contract_json,
                pack_path = excluded.pack_path
            """,
            payload,
        )
        self._conn.commit()

    def _from_row(self, row: sqlite3.Row) -> InstalledSkill:
        manifest_data = json.loads(row["manifest_json"])
        body = row["body"]
        manifest = SkillManifest(
            name=manifest_data["name"],
            description=manifest_data["description"],
            license=manifest_data.get("license"),
            compatibility=manifest_data.get("compatibility"),
            allowed_tools=tuple(manifest_data.get("allowed_tools") or ()),
            capabilities=tuple(manifest_data.get("capabilities") or ()),
            permissions=tuple(manifest_data.get("permissions") or ()),
            scope=manifest_data.get("scope") or row["scope"],
            metadata=dict(manifest_data.get("metadata") or {}),
            body=body,
        )
        scan_data = json.loads(row["scan_json"])
        scan = SkillScan(
            files=tuple(scan_data.get("files") or ()),
            scripts=tuple(scan_data.get("scripts") or ()),
            assets=tuple(scan_data.get("assets") or ()),
            declared_permissions=tuple(scan_data.get("declared_permissions") or ()),
            inferred_permissions=tuple(scan_data.get("inferred_permissions") or ()),
            findings=tuple(
                ScanFinding(
                    path=str(item.get("path", "")),
                    code=str(item.get("code", "")),
                    detail=str(item.get("detail", "")),
                    severity=str(item.get("severity", "error")),
                )
                for item in scan_data.get("findings") or ()
            ),
            executed_scripts=bool(scan_data.get("executed_scripts", False)),
            malicious=bool(scan_data.get("malicious", False)),
        )
        contract = None
        if row["contract_json"]:
            raw = json.loads(row["contract_json"])
            contract = RegressionContract(
                skill=str(raw.get("skill") or row["name"]),
                prompt=str(raw.get("prompt") or ""),
                verification=tuple(raw.get("verification") or ()),
                forbidden=tuple(raw.get("forbidden") or ()),
            )
        return InstalledSkill(
            id=row["id"],
            name=row["name"],
            revision=row["revision"],
            locator=row["locator"],
            status=row["status"],
            scope=row["scope"],
            repository_id=row["repository_id"],
            manifest=manifest,
            scan=scan,
            contract=contract,
            pack_path=row["pack_path"],
        )


def bundled_skills_root() -> Path:
    from os import environ

    env = environ.get("KRONOS_SKILLS_HOME")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "skills"
        if (candidate / "core").is_dir():
            return candidate
    return Path("skills")


def _contract_for(pack: Path, regression_root: Path, name: str) -> RegressionContract | None:
    for candidate in (pack / "regression.yaml", regression_root / f"{name}.yaml"):
        if candidate.is_file():
            return load_regression_contract(candidate)
    return None


def _skill_payload(skill: InstalledSkill) -> tuple[object, ...]:
    manifest = {
        "name": skill.manifest.name,
        "description": skill.manifest.description,
        "license": skill.manifest.license,
        "compatibility": skill.manifest.compatibility,
        "allowed_tools": list(skill.manifest.allowed_tools),
        "capabilities": list(skill.manifest.capabilities),
        "permissions": list(skill.manifest.permissions),
        "scope": skill.manifest.scope,
        "metadata": skill.manifest.metadata,
    }
    scan = {
        "files": list(skill.scan.files),
        "scripts": list(skill.scan.scripts),
        "assets": list(skill.scan.assets),
        "declared_permissions": list(skill.scan.declared_permissions),
        "inferred_permissions": list(skill.scan.inferred_permissions),
        "findings": [
            {
                "path": item.path,
                "code": item.code,
                "detail": item.detail,
                "severity": item.severity,
            }
            for item in skill.scan.findings
        ],
        "executed_scripts": skill.scan.executed_scripts,
        "malicious": skill.scan.malicious,
    }
    contract = None
    if skill.contract is not None:
        contract = json.dumps(
            {
                "skill": skill.contract.skill,
                "prompt": skill.contract.prompt,
                "verification": list(skill.contract.verification),
                "forbidden": list(skill.contract.forbidden),
            }
        )
    return (
        skill.id,
        skill.name,
        skill.revision,
        skill.locator,
        skill.status,
        skill.scope,
        skill.repository_id,
        json.dumps(manifest),
        skill.manifest.body,
        json.dumps(scan),
        contract,
        skill.pack_path,
    )


def skill_to_dict(skill: InstalledSkill, *, include_body: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": skill.id,
        "name": skill.name,
        "revision": skill.revision,
        "locator": skill.locator,
        "status": skill.status,
        "scope": skill.scope,
        "repository_id": skill.repository_id,
        "description": skill.manifest.description,
        "capabilities": list(skill.manifest.capabilities),
        "permissions": list(skill.manifest.permissions),
        "scan": {
            "malicious": skill.scan.malicious,
            "executed_scripts": skill.scan.executed_scripts,
            "files": list(skill.scan.files),
            "scripts": list(skill.scan.scripts),
            "assets": list(skill.scan.assets),
            "declared_permissions": list(skill.scan.declared_permissions),
            "inferred_permissions": list(skill.scan.inferred_permissions),
            "findings": [
                {"path": item.path, "code": item.code, "detail": item.detail}
                for item in skill.scan.findings
            ],
        },
    }
    if include_body:
        payload["body"] = skill.manifest.body
    return payload
