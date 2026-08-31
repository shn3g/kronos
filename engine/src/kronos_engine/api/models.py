# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP response models. No business rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


class VersionResponse(BaseModel):
    engine_version: str
    min_client_version: str
    compatible: bool


class RepositoryRecord(BaseModel):
    id: str
    display_name: str
    realpath: str
    origin: str | None
    status: str


class RepositoryListResponse(BaseModel):
    repositories: list[RepositoryRecord]


class PathRequest(BaseModel):
    path: str
    policy: dict[str, Any] | None = None


class PreviewFileModel(BaseModel):
    path: str
    action: str
    content: str
    unified_diff: str


class InspectResponse(BaseModel):
    git_root: str
    origin: str | None
    current_branch: str
    default_branch: str
    languages: list[str]
    package_managers: list[str]
    policy: dict[str, Any]
    preview: list[PreviewFileModel]
    wrote_files: bool
    committed: bool
    pushed: bool


class RepositoryDetailResponse(BaseModel):
    repository: RepositoryRecord
    policy: dict[str, Any]
    runtime: dict[str, str]
    preview: list[PreviewFileModel] | None = None
    wrote_files: bool = False
    committed: bool = False
    pushed: bool = False


class GoalListResponse(BaseModel):
    goals: list[dict[str, str]]


class EventItem(BaseModel):
    seq: int
    id: str
    type: str
    payload: dict[str, Any]
    recorded_at: str


class EventListResponse(BaseModel):
    events: list[EventItem]
    head_seq: int


class ProviderModel(BaseModel):
    id: str
    kind: str
    display_name: str
    base_url: str | None
    billed: bool


class ProfileModel(BaseModel):
    id: str
    display_name: str
    role: str
    provider_id: str
    model_id: str
    billed: bool
    approved_fallbacks: list[str]


class DetectedToolModel(BaseModel):
    kind: str
    label: str
    present: bool


class ModelsSnapshotResponse(BaseModel):
    detected: list[DetectedToolModel]
    providers: list[ProviderModel]
    profiles: list[ProfileModel]
    assignments: dict[str, str | None]


class ProviderCreateRequest(BaseModel):
    kind: str
    display_name: str
    base_url: str | None = None
    billed: bool = False
    api_key: str | None = None


class ProviderCreateResponse(BaseModel):
    provider: ProviderModel
    profile: ProfileModel
    profiles: list[ProfileModel]


class AssignmentsRequest(BaseModel):
    planner: str = ""
    coder: str = ""
    reviewer: str = ""
    embedding: str = ""
    confirm_shared_roles: bool = False


class AssignmentsResponse(BaseModel):
    assignments: dict[str, str | None]


class IndexStatusResponse(BaseModel):
    repository_id: str
    commit: str | None
    chunk_count: int
    dense_available: bool
    index_path: str
    disk_bytes: int
    ready: bool


class IndexSearchHit(BaseModel):
    path: str
    start_line: int
    end_line: int
    commit: str
    symbol: str | None
    rank_sources: list[str]
    trust: str
    text: str


class IndexSearchResponse(BaseModel):
    items: list[IndexSearchHit]


class IndexMapResponse(BaseModel):
    text: str


class GithubAppStatusModel(BaseModel):
    registered: bool
    installed: bool
    verified: bool
    app_id: int | None = None
    slug: str | None = None
    create_url: str = "https://github.com/settings/apps/new"
    install_url: str | None = None


class GithubEnrolledModel(BaseModel):
    owner: str
    repo: str
    integration_branch: str
    protected_branch: str


class GithubStatusResponse(BaseModel):
    controller: GithubAppStatusModel
    reviewer: GithubAppStatusModel
    webhook_enabled: bool
    poll_mode: str
    github_cli_present: bool
    enrolled: GithubEnrolledModel | None = None


class GithubManifestsResponse(BaseModel):
    controller: dict[str, Any]
    reviewer: dict[str, Any]
    reviewer_check_name: str


class GithubAppRecordResponse(BaseModel):
    role: str
    registered: bool
    installed: bool
    verified: bool
    app_id: int | None = None
    slug: str | None = None


class GithubInstallRequest(BaseModel):
    installation_id: int


class GithubManifestConvertRequest(BaseModel):
    code: str
    gh_token: str | None = None


class GithubRulesetRequest(BaseModel):
    owner: str
    repo: str
    integration_branch: str = "integration"
    protected_branch: str = "main"
    reviewer_integration_id: int
    confirm: bool = False
