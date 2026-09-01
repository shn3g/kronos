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


class GoalModel(BaseModel):
    id: str
    repository_id: str
    title: str
    state: str
    source: str
    risk_ceiling: str
    success_criteria: str
    non_goals: str
    stop_reason: str | None = None
    schedule: str | None = None
    max_attempts: int = 3


class GoalListResponse(BaseModel):
    goals: list[GoalModel]


class GoalCreateRequest(BaseModel):
    repository_id: str
    title: str
    success_criteria: str
    non_goals: str
    risk_ceiling: str
    source: str = "desktop"
    schedule: str | None = None
    max_attempts: int


class GoalTickResponse(BaseModel):
    ok: bool
    status: str
    reason: str
    task_id: str | None = None
    pr_url: str | None = None
    terminal: bool = False


class GoalIngestRequest(BaseModel):
    source: str
    repository_id: str
    title: str
    non_goals: str
    risk_ceiling: str
    max_attempts: int
    body: str = ""
    success_criteria: str = ""
    schedule: str | None = None


class TaskModel(BaseModel):
    id: str
    goal_id: str
    title: str
    state: str
    kind: str
    stop_reason: str | None = None
    pr_url: str | None = None
    pr_base: str | None = None


class GoalDetailResponse(BaseModel):
    goal: GoalModel
    tasks: list[TaskModel]


class RunModel(BaseModel):
    id: str
    goal_id: str
    task_id: str
    status: str
    evidence: str
    pr_url: str | None = None


class RunListResponse(BaseModel):
    runs: list[RunModel]


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


class EmbeddingBackendModel(BaseModel):
    kind: Literal["openai_compatible", "onnx", "none"]
    model_id: str
    display_name: str


class ModelsSnapshotResponse(BaseModel):
    detected: list[DetectedToolModel]
    providers: list[ProviderModel]
    profiles: list[ProfileModel]
    assignments: dict[str, str | None]
    embedding_backend: EmbeddingBackendModel


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
    state: str
    files_done: int
    files_total: int
    chunks_embedded: int
    chunks_skipped: int
    last_activity_at: str | None
    watch_enabled: bool


class IndexWatchRequest(BaseModel):
    enabled: bool


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


class SkillImportRequest(BaseModel):
    locator: str
    revision: str
    scope: str | None = None
    repository_id: str | None = None


class SkillApproveRequest(BaseModel):
    human: bool = False


class SkillRouteRequest(BaseModel):
    query: str
    budget_tokens: int = 200
    selected_name: str | None = None


class LessonImportRequest(BaseModel):
    yaml: str


class TelegramTokenRequest(BaseModel):
    token: str


class TelegramAllowlistRequest(BaseModel):
    allowed_user_ids: list[int]
    allowed_chat_ids: list[int]
    default_repository_id: str | None = None


class TelegramStatusResponse(BaseModel):
    token_present: bool
    allowed_user_ids: list[int]
    allowed_chat_ids: list[int]
    default_repository_id: str | None = None
    last_update_offset: int
    botfather_url: str
    setup_steps: list[str]


class BackupRequest(BaseModel):
    dest: str = ""


class OpsSettingsRequest(BaseModel):
    otel_export: bool = False
    langfuse_export: bool = False

