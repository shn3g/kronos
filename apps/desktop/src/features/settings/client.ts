// SPDX-License-Identifier: AGPL-3.0-or-later

export interface OpsSettingsView {
  otelExport: boolean;
  langfuseExport: boolean;
}

export interface SettingsPageClients {
  load(): Promise<OpsSettingsView>;
  save(next: OpsSettingsView): Promise<OpsSettingsView>;
  doctor(): Promise<{ ready: boolean; findings: string[] }>;
  backup(): Promise<{ path: string; includesSecretStore: boolean }>;
}

interface EngineJsonResponse {
  status: number;
  body: string;
}

export function createProductionSettingsClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): SettingsPageClients {
  return {
    async load() {
      const payload = await jsonRequest(request, "GET", "/ops/settings");
      return {
        otelExport: payload.otel_export === true,
        langfuseExport: payload.langfuse_export === true,
      };
    },
    async save(next) {
      const payload = await jsonRequest(request, "PUT", "/ops/settings", {
        otel_export: next.otelExport,
        langfuse_export: next.langfuseExport,
      });
      return {
        otelExport: payload.otel_export === true,
        langfuseExport: payload.langfuse_export === true,
      };
    },
    async doctor() {
      const payload = await jsonRequest(request, "GET", "/ops/doctor");
      const findings = Array.isArray(payload.findings)
        ? payload.findings.filter((item): item is string => typeof item === "string")
        : [];
      return { ready: payload.ready === true, findings };
    },
    async backup() {
      const payload = await jsonRequest(request, "POST", "/ops/backup", {});
      return {
        path: typeof payload.path === "string" ? payload.path : "",
        includesSecretStore: payload.includes_secret_store === true,
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
