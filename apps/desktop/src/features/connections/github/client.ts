// SPDX-License-Identifier: AGPL-3.0-or-later

export type GitHubAppRole = "controller" | "reviewer";

export interface GitHubAppStatus {
  registered: boolean;
  installed: boolean;
  verified: boolean;
}

export interface GitHubConnectionStatus {
  controller: GitHubAppStatus;
  reviewer: GitHubAppStatus;
  webhookEnabled: boolean;
  pollMode: string;
  githubCliPresent: boolean;
}

export interface GitHubManifests {
  controller: { name: string };
  reviewer: { name: string };
  reviewerCheckName: string;
}

export interface GitHubAppActionResult {
  role: string;
  registered?: boolean;
  installed?: boolean;
  verified?: boolean;
}

export interface RulesetProposalView {
  strict: boolean;
  requiredChecks: { context: string; integrationId: number | null }[];
}

export interface GitHubClient {
  status(): Promise<GitHubConnectionStatus>;
  manifests(): Promise<GitHubManifests>;
  registerApp(
    role: GitHubAppRole,
    draft: { appId: number; slug: string; privateKey: string },
  ): Promise<GitHubAppActionResult>;
  recordInstallation(role: GitHubAppRole, installationId: number): Promise<GitHubAppActionResult>;
  verify(role: GitHubAppRole): Promise<GitHubAppActionResult>;
  proposeRuleset(input: {
    owner: string;
    repo: string;
    reviewerIntegrationId: number;
  }): Promise<RulesetProposalView>;
  applyRuleset(input: {
    owner: string;
    repo: string;
    reviewerIntegrationId: number;
    confirm: boolean;
  }): Promise<{ applied: boolean }>;
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
      };
    },
    async manifests() {
      const payload = await jsonRequest(request, "GET", "/github/manifests");
      return {
        controller: { name: stringField(asRecord(payload.controller), "name") },
        reviewer: { name: stringField(asRecord(payload.reviewer), "name") },
        reviewerCheckName: stringField(payload, "reviewer_check_name"),
      };
    },
    async registerApp(role, draft) {
      const payload = await jsonRequest(request, "POST", `/github/apps/${role}`, {
        app_id: draft.appId,
        slug: draft.slug,
        private_key: draft.privateKey,
      });
      return {
        role: stringField(payload, "role") || role,
        registered: payload.registered === true,
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
        confirm: input.confirm,
      });
      return { applied: true };
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
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
