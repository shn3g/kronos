// SPDX-License-Identifier: AGPL-3.0-or-later

export interface MemoryRecord {
  id: string;
  kind: string;
  text: string;
  sourceSha: string;
  outcome: string;
  confidence: number;
  helpful: number;
  harmful: number;
  status: string;
  skillId: string | null;
}

export interface MemoryClient {
  list(): Promise<MemoryRecord[]>;
  importLessons(yaml: string): Promise<MemoryRecord[]>;
}

interface EngineJsonResponse {
  status: number;
  body: string;
}

export function createProductionMemoryClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): MemoryClient {
  return {
    async list() {
      const payload = await jsonRequest(request, "GET", "/memory");
      const items = Array.isArray(payload.records) ? payload.records : [];
      return items.map(mapRecord);
    },
    async importLessons(yaml) {
      const payload = await jsonRequest(request, "POST", "/memory/import-lessons", { yaml });
      const items = Array.isArray(payload.records) ? payload.records : [];
      return items.map(mapRecord);
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

function mapRecord(raw: unknown): MemoryRecord {
  const item = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
  return {
    id: typeof item.id === "string" ? item.id : "",
    kind: typeof item.kind === "string" ? item.kind : "",
    text: typeof item.text === "string" ? item.text : "",
    sourceSha: typeof item.source_sha === "string" ? item.source_sha : "",
    outcome: typeof item.outcome === "string" ? item.outcome : "",
    confidence: typeof item.confidence === "number" ? item.confidence : 0,
    helpful: typeof item.helpful === "number" ? item.helpful : 0,
    harmful: typeof item.harmful === "number" ? item.harmful : 0,
    status: typeof item.status === "string" ? item.status : "",
    skillId: typeof item.skill_id === "string" ? item.skill_id : null,
  };
}
