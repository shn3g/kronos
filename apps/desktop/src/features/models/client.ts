// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export type ModelRole = "orchestrator" | "planner" | "coder" | "reviewer" | "embedding";
export type EmbeddingBackendKind = "openai_compatible" | "onnx" | "none";

export interface DetectedTool {
  kind: string;
  label: string;
  present: boolean;
}

export interface ResourceLimits {
  maxTokens: number;
  maxAttempts: number;
  timeoutSeconds: number;
  costCeiling: number;
}

export interface ModelProfileOption {
  id: string;
  displayName: string;
  role: string;
  billed: boolean;
  modelId: string;
  limits: ResourceLimits;
}

export interface ProviderDraft {
  kind: string;
  displayName: string;
  baseUrl: string | null;
  billed: boolean;
  apiKey?: string | null;
  modelId?: string | null;
}

export interface CreatedProvider {
  provider: { id: string; kind: string; displayName: string; billed: boolean };
  profiles: ModelProfileOption[];
}

export type RoleAssignments = Record<ModelRole, string | null>;

export interface EmbeddingBackend {
  kind: EmbeddingBackendKind;
  modelId: string;
  displayName: string;
}

export interface ModelsSnapshot {
  detected: DetectedTool[];
  profiles: ModelProfileOption[];
  assignments: RoleAssignments;
  embeddingBackend: EmbeddingBackend;
}

export interface ProfileUpdate {
  modelId: string;
  limits: ResourceLimits;
}

export interface ModelsClient {
  snapshot(): Promise<ModelsSnapshot>;
  assign(
    assignments: Record<ModelRole, string>,
    options?: { confirmSharedRoles?: boolean },
  ): Promise<RoleAssignments>;
  createProvider(draft: ProviderDraft): Promise<CreatedProvider>;
  updateProfile(id: string, patch: ProfileUpdate): Promise<ModelProfileOption>;
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
    async assign(assignments, options) {
      const body: Record<string, string | boolean> = { ...assignments };
      if (options?.confirmSharedRoles) {
        body.confirm_shared_roles = true;
      }
      const payload = await jsonRequest(request, "PUT", "/models/assignments", body);
      return mapAssignments(asRecord(payload.assignments));
    },
    async createProvider(draft) {
      const payload = await jsonRequest(request, "POST", "/models/providers", {
        kind: draft.kind,
        display_name: draft.displayName,
        base_url: draft.baseUrl,
        billed: draft.billed,
        ...(draft.apiKey ? { api_key: draft.apiKey } : {}),
        ...(draft.modelId ? { model_id: draft.modelId } : {}),
      });
      return mapCreatedProvider(payload);
    },
    async updateProfile(id, patch) {
      const payload = await jsonRequest(request, "PUT", `/models/profiles/${id}`, {
        model_id: patch.modelId,
        limits: {
          max_tokens: patch.limits.maxTokens,
          max_attempts: patch.limits.maxAttempts,
          timeout_seconds: patch.limits.timeoutSeconds,
          cost_ceiling: patch.limits.costCeiling,
        },
      });
      return mapProfile(payload);
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
    profiles: profilesRaw.map(mapProfile),
    assignments: mapAssignments(asRecord(payload.assignments)),
    embeddingBackend: mapEmbeddingBackend(payload.embedding_backend),
  };
}

function mapEmbeddingBackend(raw: unknown): EmbeddingBackend {
  const record = asRecord(raw);
  const kind = record.kind;
  if (kind === "openai_compatible" || kind === "onnx" || kind === "none") {
    return {
      kind,
      modelId: stringField(record, "model_id"),
      displayName: stringField(record, "display_name") || defaultBackendName(kind),
    };
  }
  return { kind: "none", modelId: "", displayName: "Sparse only" };
}

function defaultBackendName(kind: EmbeddingBackendKind): string {
  if (kind === "onnx") {
    return "Local ONNX";
  }
  if (kind === "openai_compatible") {
    return "OpenAI-compatible";
  }
  return "Sparse only";
}

function mapCreatedProvider(payload: Record<string, unknown>): CreatedProvider {
  const provider = asRecord(payload.provider);
  const profilesRaw = Array.isArray(payload.profiles) ? payload.profiles : [];
  return {
    provider: {
      id: stringField(provider, "id"),
      kind: stringField(provider, "kind"),
      displayName: stringField(provider, "display_name") || stringField(provider, "id"),
      billed: provider.billed === true,
    },
    profiles: profilesRaw.map(mapProfile),
  };
}

function mapProfile(item: unknown): ModelProfileOption {
  const profile = asRecord(item);
  return {
    id: stringField(profile, "id"),
    displayName: stringField(profile, "display_name") || stringField(profile, "id"),
    role: stringField(profile, "role"),
    billed: profile.billed === true,
    modelId: stringField(profile, "model_id"),
    limits: mapLimits(profile.limits),
  };
}

function mapLimits(raw: unknown): ResourceLimits {
  const record = asRecord(raw);
  return {
    maxTokens: numberField(record, "max_tokens"),
    maxAttempts: numberField(record, "max_attempts"),
    timeoutSeconds: numberField(record, "timeout_seconds"),
    costCeiling: numberField(record, "cost_ceiling"),
  };
}

function mapAssignments(raw: Record<string, unknown>): RoleAssignments {
  return {
    orchestrator: stringOrNull(raw.orchestrator),
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

function numberField(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
