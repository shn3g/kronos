// SPDX-License-Identifier: AGPL-3.0-or-later

export type ModelRole = "planner" | "coder" | "reviewer" | "embedding";

export interface DetectedTool {
  kind: string;
  label: string;
  present: boolean;
}

export interface ModelProfileOption {
  id: string;
  displayName: string;
  role: string;
  billed: boolean;
}

export type RoleAssignments = Record<ModelRole, string | null>;

export interface ModelsSnapshot {
  detected: DetectedTool[];
  profiles: ModelProfileOption[];
  assignments: RoleAssignments;
}

export interface ModelsClient {
  snapshot(): Promise<ModelsSnapshot>;
  assign(assignments: Record<ModelRole, string>): Promise<RoleAssignments>;
}

interface EngineJsonResponse {
  status: number;
  body: string;
}

export function createProductionModelsClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): ModelsClient {
  return {
    async snapshot() {
      const payload = await jsonRequest(request, "GET", "/models");
      return mapSnapshot(payload);
    },
    async assign(assignments) {
      const payload = await jsonRequest(request, "PUT", "/models/assignments", assignments);
      return mapAssignments(asRecord(payload.assignments));
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

function mapSnapshot(payload: Record<string, unknown>): ModelsSnapshot {
  const detectedRaw = Array.isArray(payload.detected) ? payload.detected : [];
  const profilesRaw = Array.isArray(payload.profiles) ? payload.profiles : [];
  return {
    detected: detectedRaw.map((item) => {
      const tool = asRecord(item);
      return {
        kind: stringField(tool, "kind"),
        label: stringField(tool, "label"),
        present: tool.present === true,
      };
    }),
    profiles: profilesRaw.map((item) => {
      const profile = asRecord(item);
      return {
        id: stringField(profile, "id"),
        displayName: stringField(profile, "display_name") || stringField(profile, "id"),
        role: stringField(profile, "role"),
        billed: profile.billed === true,
      };
    }),
    assignments: mapAssignments(asRecord(payload.assignments)),
  };
}

function mapAssignments(raw: Record<string, unknown>): RoleAssignments {
  return {
    planner: stringOrNull(raw.planner),
    coder: stringOrNull(raw.coder),
    reviewer: stringOrNull(raw.reviewer),
    embedding: stringOrNull(raw.embedding),
  };
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
