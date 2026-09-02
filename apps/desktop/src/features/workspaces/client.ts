// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export type RepositoryStatus = "active" | "paused" | "disabled";

export interface EnrolledRepository {
  id: string;
  displayName: string;
  realpath: string;
  origin: string | null;
  status: RepositoryStatus;
}

export interface PreviewFile {
  path: string;
  action: string;
  content: string;
  unifiedDiff: string;
}

export interface InspectResult {
  gitRoot: string;
  origin: string | null;
  currentBranch: string;
  defaultBranch: string;
  languages: string[];
  packageManagers: string[];
  policy: Record<string, unknown>;
  preview: PreviewFile[];
  wroteFiles: boolean;
  committed: boolean;
  pushed: boolean;
}

export interface WorkspaceFileChange {
  path: string;
  summary: string;
  patch: string;
  status: string;
  fromChat: boolean;
}

export interface RepositoriesClient {
  list(): Promise<EnrolledRepository[]>;
  inspect(path: string): Promise<InspectResult>;
  enrol(path: string, policy?: Record<string, unknown>): Promise<EnrolledRepository>;
  pause(id: string): Promise<EnrolledRepository>;
  disable(id: string): Promise<EnrolledRepository>;
  resume(id: string): Promise<EnrolledRepository>;
  listChanges(id: string): Promise<WorkspaceFileChange[]>;
  writeFile(id: string, path: string, content: string): Promise<void>;
}

export async function pickRepositoryFolder(): Promise<string | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const path = await invoke<string | null>("pick_repository_folder");
    return path ?? null;
  } catch {
    return null;
  }
}

export function createProductionRepositoriesClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): RepositoriesClient {
  return {
    async list() {
      const payload = await jsonRequest(request, "GET", "/repositories");
      const repositories = Array.isArray(payload.repositories) ? payload.repositories : [];
      return repositories.map(mapRepository);
    },
    async inspect(path: string) {
      const payload = await jsonRequest(request, "POST", "/repositories/inspect", { path });
      return mapInspect(payload);
    },
    async enrol(path: string, policy?: Record<string, unknown>) {
      const payload = await jsonRequest(request, "POST", "/repositories", { path, policy });
      return mapRepository(payload.repository);
    },
    async pause(id: string) {
      const payload = await jsonRequest(request, "POST", `/repositories/${id}/pause`);
      return mapRepository(payload.repository);
    },
    async disable(id: string) {
      const payload = await jsonRequest(request, "POST", `/repositories/${id}/disable`);
      return mapRepository(payload.repository);
    },
    async resume(id: string) {
      const payload = await jsonRequest(request, "POST", `/repositories/${id}/resume`);
      return mapRepository(payload.repository);
    },
    async listChanges(id: string) {
      const payload = await jsonRequest(request, "GET", `/repositories/${id}/changes`);
      const changes = Array.isArray(payload.changes) ? payload.changes : [];
      return changes.map(mapChange);
    },
    async writeFile(id: string, path: string, content: string) {
      await jsonRequest(request, "PUT", `/repositories/${id}/files/contents`, { path, content });
    },
  };
}

function mapChange(raw: unknown): WorkspaceFileChange {
  const item = asRecord(raw);
  return {
    path: stringField(item, "path"),
    summary: stringField(item, "summary"),
    patch: stringField(item, "patch"),
    status: stringField(item, "status"),
    fromChat: item.from_chat === true,
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

function mapRepository(raw: unknown): EnrolledRepository {
  const item = asRecord(raw);
  return {
    id: stringField(item, "id"),
    displayName: stringField(item, "display_name") || stringField(item, "id"),
    realpath: stringField(item, "realpath"),
    origin: typeof item.origin === "string" ? item.origin : null,
    status: parseStatus(item.status),
  };
}

function mapInspect(payload: Record<string, unknown>): InspectResult {
  const previewRaw = Array.isArray(payload.preview) ? payload.preview : [];
  return {
    gitRoot: stringField(payload, "git_root"),
    origin: typeof payload.origin === "string" ? payload.origin : null,
    currentBranch: stringField(payload, "current_branch"),
    defaultBranch: stringField(payload, "default_branch"),
    languages: stringList(payload.languages),
    packageManagers: stringList(payload.package_managers),
    policy: asRecord(payload.policy),
    preview: previewRaw.map((item) => {
      const file = asRecord(item);
      return {
        path: stringField(file, "path"),
        action: stringField(file, "action"),
        content: stringField(file, "content"),
        unifiedDiff: stringField(file, "unified_diff"),
      };
    }),
    wroteFiles: payload.wrote_files === true,
    committed: payload.committed === true,
    pushed: payload.pushed === true,
  };
}

function parseStatus(value: unknown): RepositoryStatus {
  if (value === "paused" || value === "disabled" || value === "active") {
    return value;
  }
  return "active";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
