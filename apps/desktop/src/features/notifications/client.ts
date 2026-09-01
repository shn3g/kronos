// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export interface AlertView {
  id: string;
  title: string;
  detail: string;
  severity: string;
}

export interface NotificationsPageClients {
  list(): Promise<AlertView[]>;
}

export function createProductionNotificationsClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): NotificationsPageClients {
  return {
    async list() {
      const payload = await jsonRequest(request, "GET", "/ops/notifications");
      const items = Array.isArray(payload.items) ? payload.items : [];
      return items.map((item) => {
        const row = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
        return {
          id: typeof row.id === "string" ? row.id : "",
          title: typeof row.title === "string" ? row.title : "",
          detail: typeof row.detail === "string" ? row.detail : "",
          severity: typeof row.severity === "string" ? row.severity : "pause",
        };
      });
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
