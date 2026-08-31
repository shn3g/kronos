# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guided GitHub App onboarding. Keys stay in SecretStore; gh is optional for setup."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from kronos_engine.adapters.github import GitHubForge
from kronos_engine.adapters.github.auth import KEY_REFS, InstallationAuth
from kronos_engine.adapters.github.client import GitHubClient, HttpTransport
from kronos_engine.config.repository import TEMPLATES_ROOT
from kronos_engine.domain.github import (
    APP_ROLES,
    KRONOS_REVIEW_CHECK_NAME,
    POLL_MODE_CONDITIONAL,
)
from kronos_engine.ports.forge import (
    AppCredentials,
    ForgeAuthError,
    ForgeTarget,
    GithubAppRecord,
    GithubAppStatus,
    GithubAppStore,
    GithubConnectionStatus,
)
from kronos_engine.ports.secrets import ScopedSecret, SecretStore


class GitHubSetupService:
    def __init__(
        self,
        apps: GithubAppStore,
        secrets: SecretStore,
        transport: HttpTransport,
        *,
        webhook_enabled: bool = False,
        templates_root: Path | None = None,
    ) -> None:
        if webhook_enabled:
            raise ForgeAuthError("webhook ingress is off unless configured")
        self._apps = apps
        self._secrets = secrets
        self._transport = transport
        self._webhook_enabled = False
        self._templates = templates_root or TEMPLATES_ROOT

    def manifests(self) -> dict[str, object]:
        controller = json.loads(
            (self._templates / "github" / "controller-app-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        reviewer = json.loads(
            (self._templates / "github" / "reviewer-app-manifest.json").read_text(encoding="utf-8")
        )
        return {
            "controller": controller,
            "reviewer": reviewer,
            "reviewer_check_name": KRONOS_REVIEW_CHECK_NAME,
        }

    def status(self) -> GithubConnectionStatus:
        return GithubConnectionStatus(
            controller=self._role_status("controller"),
            reviewer=self._role_status("reviewer"),
            webhook_enabled=self._webhook_enabled,
            poll_mode=POLL_MODE_CONDITIONAL,
            github_cli_present=shutil.which("gh") is not None,
        )

    def register_app(
        self, *, role: str, app_id: int, slug: str, private_key: str
    ) -> GithubAppRecord:
        if role not in APP_ROLES:
            raise ForgeAuthError(f"unknown GitHub App role: {role}")
        if not private_key.strip():
            raise ForgeAuthError("private key is required")
        self._secrets.put(KEY_REFS[role], private_key)
        existing = self._apps.get(role)
        record = GithubAppRecord(
            role=role,
            app_id=app_id,
            slug=slug,
            installation_id=existing.installation_id if existing else None,
            verified_at=None,
        )
        self._apps.save(record)
        return record

    def record_installation(self, role: str, installation_id: int) -> GithubAppRecord:
        current = self._apps.get(role)
        if current is None:
            raise ForgeAuthError(f"{role} App is not registered")
        record = GithubAppRecord(
            role=current.role,
            app_id=current.app_id,
            slug=current.slug,
            installation_id=installation_id,
            verified_at=None,
        )
        self._apps.save(record)
        return record

    def verify_installation(self, role: str) -> GithubAppRecord:
        current = self._require_installed(role)
        auth = self._auth()
        client = GitHubClient(self._transport, auth, role=role, sleep=lambda _seconds: None)
        payload = client.request_json(
            "GET",
            f"/app/installations/{current.installation_id}",
            use_jwt=True,
        )
        if not isinstance(payload, dict) or int(payload.get("id") or 0) != current.installation_id:
            raise ForgeAuthError(f"{role} installation could not be verified")
        record = GithubAppRecord(
            role=current.role,
            app_id=current.app_id,
            slug=current.slug,
            installation_id=current.installation_id,
            verified_at=datetime.now(tz=UTC).isoformat(),
        )
        self._apps.save(record)
        return record

    def mint_installation_token(self, role: str) -> ScopedSecret:
        self._require_installed(role)
        return self._auth().mint(role)

    def forge(self, role: str, target: ForgeTarget) -> GitHubForge:
        self._require_installed(role)
        client = GitHubClient(
            self._transport, self._auth(), role=role, sleep=lambda _seconds: None
        )
        return GitHubForge(client, target)

    def _require_installed(self, role: str) -> GithubAppRecord:
        current = self._apps.get(role)
        if current is None:
            raise ForgeAuthError(f"{role} App is not registered")
        if current.installation_id is None:
            raise ForgeAuthError(f"{role} App is not installed")
        if not self._secrets.get(KEY_REFS[role]):
            raise ForgeAuthError(f"{role} App private key is missing")
        return current

    def _auth(self) -> InstallationAuth:
        apps: dict[str, AppCredentials] = {}
        for record in self._apps.list():
            apps[record.role] = AppCredentials(
                app_id=record.app_id,
                installation_id=record.installation_id or 0,
                role=record.role,
            )
        return InstallationAuth(self._secrets, apps, self._transport, sleep=lambda _seconds: None)

    def _role_status(self, role: str) -> GithubAppStatus:
        record = self._apps.get(role)
        if record is None:
            return GithubAppStatus(registered=False, installed=False, verified=False)
        return GithubAppStatus(
            registered=True,
            installed=record.installation_id is not None,
            verified=record.verified_at is not None,
        )
