// SPDX-License-Identifier: AGPL-3.0-or-later

export interface RunRecord {
  id: string;
  goalId: string;
  taskId: string;
  status: string;
  evidence: string;
  prUrl: string | null;
}

export interface RunsClient {
  list(): Promise<RunRecord[]>;
}

interface EngineJsonResponse {
  status: number;
  body: string;
}

export function createProductionRunsClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): RunsClient {
  return {
    async list() {
      const payload = await jsonRequest(request, "GET", "/runs");
      const items = Array.isArray(payload.runs) ? payload.runs : [];
      return items.map(mapRun);
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

function mapRun(raw: unknown): RunRecord {
  const item = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
  return {
    id: typeof item.id === "string" ? item.id : "",
    goalId: typeof item.goal_id === "string" ? item.goal_id : "",
    taskId: typeof item.task_id === "string" ? item.task_id : "",
    status: typeof item.status === "string" ? item.status : "",
    evidence: typeof item.evidence === "string" ? item.evidence : "",
    prUrl: typeof item.pr_url === "string" ? item.pr_url : null,
  };
}
