// SPDX-License-Identifier: AGPL-3.0-or-later

export type GitHubAppRole = "controller" | "reviewer";

export interface GitHubAppStatus {
  registered: boolean;
  installed: boolean;
  verified: boolean;
  appId: number | null;
  slug: string | null;
  createUrl: string;
  installUrl: string | null;
}

export interface GitHubEnrolledOrigin {
  owner: string;
  repo: string;
  integrationBranch: string;
  protectedBranch: string;
  repositoryId: string;
}

export interface SafetyCheck {
  id: string;
  ok: boolean;
  detail: string;
}

export interface RepositorySafety {
  ok: boolean;
  checks: SafetyCheck[];
}

export interface GitHubConnectionStatus {
  controller: GitHubAppStatus;
  reviewer: GitHubAppStatus;
  webhookEnabled: boolean;
  pollMode: string;
  githubCliPresent: boolean;
  enrolled: GitHubEnrolledOrigin | null;
}

export interface GitHubManifests {
  controller: Record<string, unknown>;
  reviewer: Record<string, unknown>;
  reviewerCheckName: string;
}

export interface GitHubAppActionResult {
  role: string;
  registered?: boolean;
  installed?: boolean;
  verified?: boolean;
  appId?: number | null;
  slug?: string;
}

export interface RulesetProposalView {
  strict: boolean;
  requiredChecks: { context: string; integrationId: number | null }[];
}

export interface GitHubClient {
  status(): Promise<GitHubConnectionStatus>;
  manifests(): Promise<GitHubManifests>;
  convertManifest(role: GitHubAppRole, code: string): Promise<GitHubAppActionResult>;
  recordInstallation(role: GitHubAppRole, installationId: number): Promise<GitHubAppActionResult>;
  verify(role: GitHubAppRole): Promise<GitHubAppActionResult>;
  proposeRuleset(input: {
    owner: string;
    repo: string;
    reviewerIntegrationId: number;
    integrationBranch?: string;
  }): Promise<RulesetProposalView>;
  applyRuleset(input: {
    owner: string;
    repo: string;
    reviewerIntegrationId: number;
    integrationBranch?: string;
    confirm: boolean;
  }): Promise<{ applied: boolean }>;
  safety(repositoryId: string): Promise<RepositorySafety>;
}

interface EngineJsonResponse {
  status: number;
  body: string;
}

export function createProductionGitHubClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): GitHubClient {
  return {
    async status() {
      const payload = await jsonRequest(request, "GET", "/github/status");
      return {
        controller: mapAppStatus(asRecord(payload.controller)),
        reviewer: mapAppStatus(asRecord(payload.reviewer)),
        webhookEnabled: payload.webhook_enabled === true,
        pollMode: stringField(payload, "poll_mode") || "conditional",
        githubCliPresent: payload.github_cli_present === true,
        enrolled: mapEnrolled(payload.enrolled),
      };
    },
    async manifests() {
      const payload = await jsonRequest(request, "GET", "/github/manifests");
      return {
        controller: asRecord(payload.controller),
        reviewer: asRecord(payload.reviewer),
        reviewerCheckName: stringField(payload, "reviewer_check_name"),
      };
    },
    async convertManifest(role, code) {
      const payload = await jsonRequest(request, "POST", `/github/apps/${role}/convert`, {
        code,
      });
      return {
        role: stringField(payload, "role") || role,
        registered: payload.registered === true,
        appId: typeof payload.app_id === "number" ? payload.app_id : null,
        slug: stringField(payload, "slug"),
      };
    },
    async recordInstallation(role, installationId) {
      const payload = await jsonRequest(request, "POST", `/github/apps/${role}/install`, {
        installation_id: installationId,
      });
      return {
        role: stringField(payload, "role") || role,
        installed: payload.installed === true,
      };
    },
    async verify(role) {
      const payload = await jsonRequest(request, "POST", `/github/apps/${role}/verify`);
      return {
        role: stringField(payload, "role") || role,
        verified: payload.verified === true,
      };
    },
    async proposeRuleset(input) {
      const payload = await jsonRequest(request, "POST", "/github/rulesets/propose", {
        owner: input.owner,
        repo: input.repo,
        reviewer_integration_id: input.reviewerIntegrationId,
        integration_branch: input.integrationBranch,
      });
      const checks = Array.isArray(payload.required_checks) ? payload.required_checks : [];
      return {
        strict: payload.strict === true,
        requiredChecks: checks.map((item) => {
          const check = asRecord(item);
          const integration = check.integration_id;
          return {
            context: stringField(check, "context"),
            integrationId: typeof integration === "number" ? integration : null,
          };
        }),
      };
    },
    async applyRuleset(input) {
      await jsonRequest(request, "POST", "/github/rulesets/apply", {
        owner: input.owner,
        repo: input.repo,
        reviewer_integration_id: input.reviewerIntegrationId,
        integration_branch: input.integrationBranch,
        confirm: input.confirm,
      });
      return { applied: true };
    },
    async safety(repositoryId) {
      const payload = await jsonRequest(request, "GET", `/repositories/${repositoryId}/safety`);
      const checks = Array.isArray(payload.checks) ? payload.checks : [];
      return {
        ok: payload.ok === true,
        checks: checks.map((item) => {
          const check = asRecord(item);
          return {
            id: stringField(check, "id"),
            ok: check.ok === true,
            detail: stringField(check, "detail"),
          };
        }),
      };
    },
  };
}

async function requestEngineJson(
  method: string,
  path: string,
  body?: unknown,
): Promise<EngineJsonResponse> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<EngineJsonResponse>("engine_json", { method, path, body: body ?? null });
  } catch {
    return { status: 0, body: "" };
  }
}

async function jsonRequest(
  request: (method: string, path: string, body?: unknown) => Promise<EngineJsonResponse>,
  method: string,
  path: string,
  body?: unknown,
): Promise<Record<string, unknown>> {
  const response = await request(method, path, body);
  if (response.status < 200 || response.status >= 300) {
    throw new Error(`engine request failed: ${response.status}`);
  }
  try {
    return JSON.parse(response.body) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function mapAppStatus(raw: Record<string, unknown>): GitHubAppStatus {
  return {
    registered: raw.registered === true,
    installed: raw.installed === true,
    verified: raw.verified === true,
    appId: typeof raw.app_id === "number" ? raw.app_id : null,
    slug: typeof raw.slug === "string" ? raw.slug : null,
    createUrl: stringField(raw, "create_url"),
    installUrl: typeof raw.install_url === "string" ? raw.install_url : null,
  };
}

function mapEnrolled(value: unknown): GitHubEnrolledOrigin | null {
  const item = asRecord(value);
  const owner = stringField(item, "owner");
  const repo = stringField(item, "repo");
  if (!owner || !repo) {
    return null;
  }
  return {
    owner,
    repo,
    integrationBranch: stringField(item, "integration_branch") || "integration",
    protectedBranch: stringField(item, "protected_branch") || "main",
    repositoryId: stringField(item, "repository_id"),
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
