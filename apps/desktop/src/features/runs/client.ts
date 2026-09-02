// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

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
  pollEvents(after: number): Promise<{ events: Array<{ type: string }>; headSeq: number }>;
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
    async pollEvents(after) {
      const payload = await jsonRequest(request, "GET", `/events?after=${after}`);
      const events = Array.isArray(payload.events) ? payload.events : [];
      return {
        events: events.map((item) => {
          const record =
            typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
          return { type: typeof record.type === "string" ? record.type : "" };
        }),
        headSeq: typeof payload.head_seq === "number" ? payload.head_seq : after,
      };
    },
  };
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
