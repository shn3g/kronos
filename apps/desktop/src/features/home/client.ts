// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export interface HomeRepository {
  id: string;
  displayName: string;
  realpath: string;
  origin: string | null;
  status: string;
}

export interface HomeDashboard {
  ready: boolean;
  repositories: HomeRepository[];
  schedules: Array<{ id: string; title: string; schedule: string; repositoryId?: string }>;
  budgets: Array<{
    repositoryId: string;
    attempts: number;
    dailyDispatches: number;
    breakerOpen: boolean;
  }>;
  runs: Array<{ id: string; status: string; evidence: string; repositoryId?: string }>;
  diffs: Array<{ path: string; summary: string; repositoryId?: string }>;
  tests: Array<{ name: string; passed: boolean; repositoryId?: string }>;
  index: Array<{
    repositoryId: string;
    ready: boolean;
    denseAvailable: boolean;
    chunkCount: number;
  }>;
}

export interface HomeClient {
  dashboard(): Promise<HomeDashboard>;
}

export function createProductionHomeClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): HomeClient {
  return {
    async dashboard() {
      const payload = await jsonRequest(request, "GET", "/ops/dashboard");
      const repositories = Array.isArray(payload.repositories) ? payload.repositories : [];
      const schedules = Array.isArray(payload.schedules) ? payload.schedules : [];
      const budgets = Array.isArray(payload.budgets) ? payload.budgets : [];
      const runs = Array.isArray(payload.runs) ? payload.runs : [];
      const diffs = Array.isArray(payload.diffs) ? payload.diffs : [];
      const tests = Array.isArray(payload.tests) ? payload.tests : [];
      const index = Array.isArray(payload.index) ? payload.index : [];
      return {
        ready: payload.ready === true,
        repositories: repositories.map((item) => {
          const row = asRecord(item);
          return {
            id: stringField(row, "id"),
            displayName: stringField(row, "display_name") || stringField(row, "id"),
            realpath: stringField(row, "realpath"),
            origin: typeof row.origin === "string" ? row.origin : null,
            status: stringField(row, "status") || "active",
          };
        }),
        schedules: schedules.map((item) => {
          const row = asRecord(item);
          return {
            id: stringField(row, "id"),
            title: stringField(row, "title"),
            schedule: stringField(row, "schedule"),
            repositoryId: stringField(row, "repository_id"),
          };
        }),
        budgets: budgets.map((item) => {
          const row = asRecord(item);
          const dailyDispatches =
            typeof row.daily_dispatches === "number"
              ? row.daily_dispatches
              : typeof row.attempts === "number"
                ? row.attempts
                : 0;
          return {
            repositoryId: stringField(row, "repository_id"),
            attempts: dailyDispatches,
            dailyDispatches,
            breakerOpen: row.breaker_open === true,
          };
        }),
        runs: runs.map((item) => {
          const row = asRecord(item);
          return {
            id: stringField(row, "id"),
            status: stringField(row, "status"),
            evidence: stringField(row, "evidence"),
            repositoryId: stringField(row, "repository_id"),
          };
        }),
        diffs: diffs.map((item) => {
          const row = asRecord(item);
          return {
            path: stringField(row, "path"),
            summary: stringField(row, "summary"),
            repositoryId: stringField(row, "repository_id"),
          };
        }),
        tests: tests.map((item) => {
          const row = asRecord(item);
          return {
            name: stringField(row, "name"),
            passed: row.passed === true,
            repositoryId: stringField(row, "repository_id"),
          };
        }),
        index: index.map((item) => {
          const row = asRecord(item);
          return {
            repositoryId: stringField(row, "repository_id"),
            ready: row.ready === true,
            denseAvailable: row.dense_available === true,
            chunkCount: typeof row.chunk_count === "number" ? row.chunk_count : 0,
          };
        }),
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

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
