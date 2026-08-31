# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer App installation tokens. Never reads GH_TOKEN."""

from __future__ import annotations

from kronos_engine.adapters.github.auth import InstallationAuth
from kronos_engine.adapters.github.client import HttpTransport
from kronos_engine.domain.github import REVIEWER_APP_ROLE
from kronos_engine.ports.forge import AppCredentials, ForgeAuthError
from kronos_engine.ports.secrets import ScopedSecret, SecretStore


class ReviewerAuthError(RuntimeError):
    """Raised when reviewer credentials are missing or the role is not reviewer."""


class ReviewerAuth:
    def __init__(
        self,
        secrets: SecretStore,
        credentials: AppCredentials,
        transport: HttpTransport,
        *,
        base_url: str = "https://api.github.com",
    ) -> None:
        self._role = credentials.role
        apps = {REVIEWER_APP_ROLE: credentials} if credentials.role == REVIEWER_APP_ROLE else {}
        self._inner = InstallationAuth(
            secrets=secrets,
            apps=apps,
            transport=transport,
            base_url=base_url,
        )

    def mint(self) -> ScopedSecret:
        if self._role != REVIEWER_APP_ROLE:
            raise ReviewerAuthError("reviewer auth refuses non-reviewer credentials")
        try:
            return self._inner.mint(REVIEWER_APP_ROLE)
        except ForgeAuthError as error:
            raise ReviewerAuthError(str(error)) from error
