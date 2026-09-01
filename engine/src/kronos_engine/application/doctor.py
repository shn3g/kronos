# SPDX-License-Identifier: AGPL-3.0-or-later
"""Doctor, backup/restore, dead letters, stuck leases, and dashboard snapshots."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kronos_engine.adapters.git.detection import ManifestStackDetector
from kronos_engine.adapters.git.repository import FilesystemGitInspector
from kronos_engine.adapters.git.worktrees import CacheRuntimeLayout
from kronos_engine.application.recorder import Recorder
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.config.settings import Settings
from kronos_engine.domain.entities import IdentifierError, Lease, TaskId
from kronos_engine.domain.version import client_is_compatible
from kronos_engine.indexing.service import IndexingService
from kronos_engine.observability.redaction import redact_mapping, redact_text
from kronos_engine.ports.secrets import SecretStore
from kronos_engine.state.event_store import SqliteEventStore
from kronos_engine.state.goals import SqliteGoalStore
from kronos_engine.state.leases import SqliteLeases
from kronos_engine.state.outbox import SqliteOutbox
from kronos_engine.state.repositories import SqliteRepositoryRegistry


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class HealthCheck:
    id: str
    label: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    ready: bool
    health: str
    compatible: bool
    model_degraded: bool
    index_degraded: bool
    findings: tuple[Finding, ...] = ()
    checks: tuple[HealthCheck, ...] = ()

    def __str__(self) -> str:
        return (
            f"DoctorReport(ready={self.ready}, health={self.health}, "
            f"compatible={self.compatible}, findings={[item.detail for item in self.findings]})"
        )


@dataclass(frozen=True, slots=True)
class BackupArchive:
    path: str
    includes_secret_store: bool = False


@dataclass(frozen=True, slots=True)
class RestoreResult:
    ready: bool
    health: str
    compatible: bool


@dataclass(frozen=True, slots=True)
class DeadLetter:
    id: int
    event_type: str
    payload: dict[str, Any]
    reason: str


@dataclass(frozen=True, slots=True)
class OpsSettings:
    otel_export: bool = False
    langfuse_export: bool = False


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    ready: bool
    repositories: list[dict[str, object]] = field(default_factory=list)
    schedules: list[dict[str, object]] = field(default_factory=list)
    budgets: list[dict[str, object]] = field(default_factory=list)
    runs: list[dict[str, object]] = field(default_factory=list)
    diffs: list[dict[str, object]] = field(default_factory=list)
    tests: list[dict[str, object]] = field(default_factory=list)
    index: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Alert:
    id: str
    title: str
    detail: str
    severity: str


class DoctorService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        secrets: SecretStore,
        recorder: Recorder | None = None,
        *,
        repos: RepositoryService | None = None,
        indexer: IndexingService | None = None,
    ) -> None:
        self._conn = conn
        self._settings = settings
        self._secrets = secrets
        events = SqliteEventStore(conn)
        outbox = SqliteOutbox(conn)
        self._recorder = recorder or Recorder(conn, events, outbox)
        self._repos = repos or RepositoryService(
            SqliteRepositoryRegistry(conn),
            settings.paths,
            FilesystemGitInspector(),
            ManifestStackDetector(),
            CacheRuntimeLayout(),
            indexer=indexer or IndexingService(settings.paths),
        )
        self._indexer = indexer or IndexingService(settings.paths)
        self._goals = SqliteGoalStore(conn)
        self._leases = SqliteLeases(conn)
        self._ensure_ops_tables()

    def check(self, *, client_version: str) -> DoctorReport:
        compatible = client_is_compatible(
            client_version, self._settings.min_client_version, self._settings.engine_version
        )
        findings: list[Finding] = []
        model_degraded = self._has_degradation("model")
        index_degraded = self._has_degradation("index")
        if not index_degraded:
            index_degraded = self._detect_corrupt_indexes(findings)
        findings.extend(self._degradation_findings())
        health = "ok"
        if not compatible:
            health = "failed"
        elif model_degraded or index_degraded:
            health = "degraded"
        ready = compatible and health != "failed"
        if ready and not findings:
            findings.append(Finding(code="ok", detail="engine ok"))
        return DoctorReport(
            ready=ready,
            health=health,
            compatible=compatible,
            model_degraded=model_degraded,
            index_degraded=index_degraded,
            findings=tuple(findings),
            checks=self._health_checks(
                compatible=compatible,
                model_degraded=model_degraded,
                index_degraded=index_degraded,
            ),
        )

    def backup(self, dest: Path) -> BackupArchive:
        dest.mkdir(parents=True, exist_ok=True)
        db_src = self._settings.paths.database
        if db_src.is_file():
            self._copy_sqlite(db_src, dest / "kronos.sqlite3")
        config_dest = dest / "config"
        config_dest.mkdir(parents=True, exist_ok=True)
        install = self._settings.paths.install_state
        if install.is_file():
            payload = json.loads(install.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and "auth_token" in payload:
                payload["auth_token"] = "[redacted]"
            (config_dest / "install.json").write_text(
                redact_text(json.dumps(payload)), encoding="utf-8"
            )
        logs_dest = dest / "logs"
        log_file = self._settings.paths.logs / "engine.log"
        if log_file.is_file():
            logs_dest.mkdir(parents=True, exist_ok=True)
            (logs_dest / "engine.log").write_text(
                redact_text(log_file.read_text(encoding="utf-8", errors="replace")),
                encoding="utf-8",
            )
        manifest = {
            "includes_secret_store": False,
            "engine_version": self._settings.engine_version,
        }
        (dest / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
        return BackupArchive(path=str(dest), includes_secret_store=False)

    def restore(self, archive: Path, *, client_version: str) -> RestoreResult:
        archive_db = Path(archive) / "kronos.sqlite3"
        dest = self._settings.paths.database
        compatible = client_is_compatible(
            client_version, self._settings.min_client_version, self._settings.engine_version
        )
        if not archive_db.is_file():
            return RestoreResult(ready=False, health="failed", compatible=compatible)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive_db, dest)
        restored = self._open_restored(dest)
        if restored is None:
            return RestoreResult(ready=False, health="failed", compatible=compatible)
        try:
            if not compatible:
                return RestoreResult(ready=False, health="failed", compatible=False)
            return RestoreResult(ready=True, health="ok", compatible=True)
        finally:
            restored.close()

    def record_dead_letter(
        self, event_type: str, payload: dict[str, object], reason: str
    ) -> DeadLetter:
        cleaned = redact_mapping(payload)
        created = datetime.now(tz=UTC).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO dead_letters(event_type, payload, reason, created_at) VALUES (?, ?, ?, ?)",
            (
                event_type,
                json.dumps(cleaned, separators=(",", ":"), sort_keys=True),
                reason,
                created,
            ),
        )
        self._conn.commit()
        letter_id = int(cursor.lastrowid or 0)
        return DeadLetter(id=letter_id, event_type=event_type, payload=cleaned, reason=reason)

    def inspect_dead_letters(self) -> Sequence[DeadLetter]:
        rows = self._conn.execute(
            "SELECT id, event_type, payload, reason FROM dead_letters ORDER BY id ASC"
        ).fetchall()
        return tuple(
            DeadLetter(
                id=int(row["id"]),
                event_type=row["event_type"],
                payload=redact_mapping(json.loads(row["payload"])),
                reason=row["reason"],
            )
            for row in rows
        )

    def recover_stuck_leases(self, now: datetime | None = None) -> Sequence[Lease]:
        clock = now or datetime.now(tz=UTC)
        recovered = self._leases.release_expired(now=clock)
        for lease in recovered:
            self._recorder.emit(
                "lease.recovered",
                {
                    "resource_key": lease.resource_key,
                    "holder_id": lease.holder_id,
                    "fence_token": lease.fence_token,
                },
            )
        return recovered

    def mark_model_degraded(self, target: str, detail: str) -> None:
        self._upsert_degradation("model", target, detail)

    def mark_index_degraded(self, target: str, detail: str) -> None:
        self._upsert_degradation("index", target, detail)

    def dashboard(self, *, client_version: str = "") -> DashboardSnapshot:
        report = self.check(client_version=client_version or self._settings.engine_version)
        repositories: list[dict[str, object]] = [
            {
                "id": item.id.value,
                "display_name": item.display_name,
                "realpath": item.realpath,
                "origin": item.origin,
                "status": item.status.value,
            }
            for item in self._repos.list()
        ]
        schedules: list[dict[str, object]] = [
            {
                "id": goal.id.value,
                "title": goal.title,
                "schedule": goal.schedule,
                "repository_id": goal.repository_id.value,
            }
            for goal in self._goals.list_goals()
            if goal.schedule
        ]
        budgets: list[dict[str, object]] = [
            {
                "repository_id": repo_id,
                "attempts": meter.daily_dispatches,
                "daily_dispatches": meter.daily_dispatches,
                "breaker_open": meter.breaker_open,
                "day": meter.day,
            }
            for repo_id, meter in self._goals.list_budget_meters()
        ]
        runs: list[dict[str, object]] = [
            {
                "id": run.id.value,
                "status": run.status,
                "evidence": run.evidence,
                "task_id": run.task_id.value,
                "repository_id": self._repository_id_for_task(run.task_id),
            }
            for run in self._goals.list_runs()
        ]
        diffs = self._diffs_from_events()
        tests = [
            {
                "name": "pytest",
                "passed": "fail" not in (run.evidence or "").lower(),
                "repository_id": self._repository_id_for_task(run.task_id),
            }
            for run in self._goals.list_runs()
        ]
        index: list[dict[str, object]] = []
        for repo in self._repos.list():
            try:
                status = self._indexer.status(repo.id.value)
            except Exception as error:
                self.mark_index_degraded(repo.id.value, str(error))
                index.append(
                    {
                        "repository_id": repo.id.value,
                        "ready": False,
                        "dense_available": False,
                        "chunk_count": 0,
                    }
                )
                continue
            index.append(
                {
                    "repository_id": status.repository_id,
                    "ready": status.ready,
                    "dense_available": status.dense_available,
                    "chunk_count": status.chunk_count,
                }
            )
        return DashboardSnapshot(
            ready=report.ready,
            repositories=repositories,
            schedules=schedules,
            budgets=budgets,
            runs=runs,
            diffs=diffs,
            tests=tests,
            index=index,
        )

    def notifications(self) -> Sequence[Alert]:
        alerts: list[Alert] = []
        for finding in self._degradation_findings():
            alerts.append(
                Alert(
                    id=f"deg_{finding.code}_{finding.detail[:12]}",
                    title="Index degraded" if "index" in finding.code else "Model degraded",
                    detail=finding.detail,
                    severity="pause",
                )
            )
        for letter in self.inspect_dead_letters():
            alerts.append(
                Alert(
                    id=f"dl_{letter.id}",
                    title="Dead letter",
                    detail=letter.reason,
                    severity="pause",
                )
            )
        for goal in self._goals.list_goals():
            if goal.stop_reason:
                alerts.append(
                    Alert(
                        id=f"goal_{goal.id.value}",
                        title=goal.title,
                        detail=goal.stop_reason,
                        severity="pause",
                    )
                )
        return tuple(alerts)

    def settings(self) -> OpsSettings:
        row = self._conn.execute(
            "SELECT otel_export, langfuse_export FROM ops_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return OpsSettings()
        return OpsSettings(
            otel_export=bool(row["otel_export"]),
            langfuse_export=bool(row["langfuse_export"]),
        )

    def save_settings(self, settings: OpsSettings) -> OpsSettings:
        self._conn.execute(
            "UPDATE ops_settings SET otel_export = ?, langfuse_export = ? WHERE id = 1",
            (1 if settings.otel_export else 0, 1 if settings.langfuse_export else 0),
        )
        self._conn.commit()
        return self.settings()

    def updates(self, *, client_version: str) -> dict[str, object]:
        compatible = client_is_compatible(
            client_version, self._settings.min_client_version, self._settings.engine_version
        )
        signature = self._settings.paths.config / "release.sig"
        checksums = self._settings.paths.config / "SHA256SUMS"
        sbom = self._settings.paths.config / "sbom.cdx.json"
        provenance = self._settings.paths.config / "provenance.json"
        return {
            "engine_version": self._settings.engine_version,
            "client_version": client_version,
            "compatible": compatible,
            "signed": signature.is_file(),
            "checksums_present": checksums.is_file(),
            "sbom_present": sbom.is_file(),
            "provenance_present": provenance.is_file(),
        }

    def _ensure_ops_tables(self) -> None:
        # Migrations create these; keep a defensive no-op if tests reuse a connection.
        _ = self._conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'dead_letters'").fetchone()

    def _open_restored(self, path: Path) -> sqlite3.Connection | None:
        try:
            conn = sqlite3.connect(str(path))
        except sqlite3.Error:
            return None
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.Error:
            conn.close()
            return None
        if row is None or str(row[0]).lower() != "ok":
            conn.close()
            return None
        conn.row_factory = sqlite3.Row
        return conn

    def _copy_sqlite(self, src: Path, dest: Path) -> None:
        source = sqlite3.connect(str(src))
        try:
            destination = sqlite3.connect(str(dest))
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()

    def _upsert_degradation(self, kind: str, target: str, detail: str) -> None:
        self._conn.execute(
            "INSERT INTO ops_degradation(kind, target, detail) VALUES (?, ?, ?) "
            "ON CONFLICT(kind, target) DO UPDATE SET detail = excluded.detail",
            (kind, target, redact_text(detail)),
        )
        self._conn.commit()

    def _has_degradation(self, kind: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM ops_degradation WHERE kind = ? LIMIT 1", (kind,)
        ).fetchone()
        return row is not None

    def _health_checks(
        self,
        *,
        compatible: bool,
        model_degraded: bool,
        index_degraded: bool,
    ) -> tuple[HealthCheck, ...]:
        planner = self._conn.execute(
            "SELECT profile_id FROM model_assignments WHERE role = 'planner'"
        ).fetchone()
        repo_row = self._conn.execute("SELECT COUNT(*) FROM repositories").fetchone()
        repo_count = int(repo_row[0]) if repo_row is not None else 0
        model_ok = planner is not None and not model_degraded
        secrets_ok, secrets_detail = self._secrets_health()
        return (
            HealthCheck(
                id="engine",
                label="Engine",
                ok=compatible,
                detail=(
                    "The local engine is running."
                    if compatible
                    else "This desktop cannot use the connected engine version."
                ),
            ),
            HealthCheck(
                id="model",
                label="Model",
                ok=model_ok,
                detail=(
                    "A planner model is assigned."
                    if model_ok
                    else "Connect a model before chatting."
                ),
            ),
            HealthCheck(
                id="workspace",
                label="Workspace",
                ok=repo_count > 0,
                detail=(
                    f"{repo_count} folder{'s' if repo_count != 1 else ''} enrolled."
                    if repo_count > 0
                    else "Open a git folder to index and edit code."
                ),
            ),
            HealthCheck(
                id="index",
                label="Index",
                ok=not index_degraded,
                detail=(
                    "The local search index is healthy."
                    if not index_degraded
                    else "The search index needs a rebuild."
                ),
            ),
            HealthCheck(
                id="secrets",
                label="Secrets",
                ok=secrets_ok,
                detail=secrets_detail,
            ),
        )

    def _secrets_health(self) -> tuple[bool, str]:
        try:
            self._secrets.get("kronos:health-probe")
        except Exception:
            return False, "The operating system secret store is not available."
        return True, "The operating system secret store is reachable. API keys stay there."

    def _degradation_findings(self) -> list[Finding]:
        rows = self._conn.execute("SELECT kind, target, detail FROM ops_degradation").fetchall()
        return [Finding(code=row["kind"], detail=row["detail"]) for row in rows]

    def _detect_corrupt_indexes(self, findings: list[Finding]) -> bool:
        degraded = False
        for repo in self._repos.list():
            try:
                self._indexer.status(repo.id.value)
            except Exception as error:
                self.mark_index_degraded(repo.id.value, str(error) or "corrupt cache")
                findings.append(Finding(code="index", detail="corrupt cache"))
                degraded = True
        return degraded

    def _repository_id_for_task(self, task_id: object) -> str:
        ident = task_id if isinstance(task_id, TaskId) else TaskId(str(task_id))
        try:
            return self._goals.get_task(ident).repository_id.value
        except (LookupError, IdentifierError):
            return ""

    def _diffs_from_events(self) -> list[dict[str, object]]:
        events = SqliteEventStore(self._conn).list_after(0)
        diffs: list[dict[str, object]] = []
        for item in events:
            if item.type in {"git.wrote", "external.wrote"}:
                payload = dict(item.payload)
                repo_id = str(payload.get("repository_id") or "")
                if not repo_id and payload.get("task_id"):
                    repo_id = self._repository_id_for_task(payload.get("task_id"))
                diffs.append(
                    {
                        "path": str(payload.get("path") or payload.get("url") or item.type),
                        "summary": str(payload.get("summary") or item.type),
                        "repository_id": repo_id,
                        "patch": str(payload.get("patch") or ""),
                    }
                )
        return diffs
