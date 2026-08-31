// SPDX-License-Identifier: AGPL-3.0-or-later

export interface SkillFinding {
  path: string;
  code: string;
  detail: string;
}

export interface SkillScan {
  malicious: boolean;
  executedScripts: boolean;
  files: string[];
  scripts: string[];
  permissions: string[];
  findings: SkillFinding[];
}

export interface SkillRecord {
  id: string;
  name: string;
  revision: string;
  locator: string;
  status: string;
  scope: string;
  description: string;
  capabilities: string[];
  scan: SkillScan;
}

export interface SkillsClient {
  list(): Promise<SkillRecord[]>;
  importPack(locator: string, revision: string, scope?: string): Promise<SkillRecord>;
  evaluate(id: string): Promise<SkillRecord>;
  approve(id: string, human: boolean): Promise<SkillRecord>;
  activate(id: string): Promise<SkillRecord>;
  promote(id: string, human: boolean): Promise<SkillRecord>;
  disable(id: string): Promise<SkillRecord>;
}

interface EngineJsonResponse {
  status: number;
  body: string;
}

export function createProductionSkillsClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): SkillsClient {
  return {
    async list() {
      const payload = await jsonRequest(request, "GET", "/skills");
      const items = Array.isArray(payload.skills) ? payload.skills : [];
      return items.map(mapSkill);
    },
    async importPack(locator, revision, scope) {
      const payload = await jsonRequest(request, "POST", "/skills/import", {
        locator,
        revision,
        scope: scope ?? "community",
      });
      return mapSkill(payload);
    },
    async evaluate(id) {
      const payload = await jsonRequest(request, "POST", `/skills/${id}/evaluate`);
      return mapSkill(payload);
    },
    async approve(id, human) {
      const payload = await jsonRequest(request, "POST", `/skills/${id}/approve`, { human });
      return mapSkill(payload);
    },
    async activate(id) {
      const payload = await jsonRequest(request, "POST", `/skills/${id}/activate`);
      return mapSkill(payload);
    },
    async promote(id, human) {
      await jsonRequest(request, "POST", `/skills/${id}/promote`, { human });
      const payload = await jsonRequest(request, "GET", `/skills/${id}`);
      return mapSkill(payload);
    },
    async disable(id) {
      const payload = await jsonRequest(request, "POST", `/skills/${id}/disable`);
      return mapSkill(payload);
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

function mapSkill(raw: unknown): SkillRecord {
  const item = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
  const scanRaw =
    typeof item.scan === "object" && item.scan !== null
      ? (item.scan as Record<string, unknown>)
      : {};
  const declared = Array.isArray(scanRaw.declared_permissions)
    ? scanRaw.declared_permissions.filter((entry): entry is string => typeof entry === "string")
    : [];
  const findingsRaw = Array.isArray(scanRaw.findings) ? scanRaw.findings : [];
  const capabilities = Array.isArray(item.capabilities)
    ? item.capabilities.filter((entry): entry is string => typeof entry === "string")
    : [];
  return {
    id: typeof item.id === "string" ? item.id : "",
    name: typeof item.name === "string" ? item.name : "",
    revision: typeof item.revision === "string" ? item.revision : "",
    locator: typeof item.locator === "string" ? item.locator : "",
    status: typeof item.status === "string" ? item.status : "",
    scope: typeof item.scope === "string" ? item.scope : "",
    description: typeof item.description === "string" ? item.description : "",
    capabilities,
    scan: {
      malicious: scanRaw.malicious === true,
      executedScripts: scanRaw.executed_scripts === true,
      files: Array.isArray(scanRaw.files)
        ? scanRaw.files.filter((entry): entry is string => typeof entry === "string")
        : [],
      scripts: Array.isArray(scanRaw.scripts)
        ? scanRaw.scripts.filter((entry): entry is string => typeof entry === "string")
        : [],
      permissions: declared,
      findings: findingsRaw.flatMap((entry) => {
        if (typeof entry !== "object" || entry === null) {
          return [];
        }
        const finding = entry as Record<string, unknown>;
        return [
          {
            path: typeof finding.path === "string" ? finding.path : "",
            code: typeof finding.code === "string" ? finding.code : "",
            detail: typeof finding.detail === "string" ? finding.detail : "",
          },
        ];
      }),
    },
  };
}
