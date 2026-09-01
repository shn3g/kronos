// SPDX-License-Identifier: AGPL-3.0-or-later

import type { DetectedTool, ModelRole, ProviderDraft } from "../features/models/client";

export function pickLocalOpenAiEndpoint(detected: DetectedTool[]): DetectedTool | null {
  return detected.find((item) => item.kind === "openai_compatible" && item.present) ?? null;
}

export function cursorCliDetected(detected: DetectedTool[]): boolean {
  return detected.some((item) => item.kind === "cursor_cli" && item.present);
}

export function displayNameFromEndpointLabel(label: string): string {
  if (label.includes(":11434")) {
    return "Ollama";
  }
  if (label.includes(":1234")) {
    return "LM Studio";
  }
  return "Local model";
}

export function localOpenAiProviderDraft(endpoint: DetectedTool): ProviderDraft {
  return {
    kind: "openai_compatible",
    displayName: displayNameFromEndpointLabel(endpoint.label),
    baseUrl: endpoint.label,
    billed: false,
  };
}

export function billedFromBaseUrl(url: string): boolean {
  const trimmed = url.trim().toLowerCase();
  if (trimmed === "") {
    return false;
  }
  return !(
    trimmed.includes("127.0.0.1") ||
    trimmed.includes("localhost") ||
    trimmed.includes("[::1]")
  );
}

export function hostedApiNeedsKey(url: string, apiKey: string): boolean {
  return billedFromBaseUrl(url) && apiKey.trim() === "";
}

export const MODEL_URL_PRESETS: readonly { id: string; label: string; url: string }[] = [
  { id: "ollama", label: "Ollama", url: "http://127.0.0.1:11434/v1" },
  { id: "lmstudio", label: "LM Studio", url: "http://127.0.0.1:1234/v1" },
  { id: "openai", label: "OpenAI", url: "https://api.openai.com/v1" },
];

export function assignmentsFromCreatedProfiles(
  profiles: { id: string; role: string }[],
): Record<ModelRole, string> | null {
  if (profiles.length === 0) {
    return null;
  }
  const byRole = Object.fromEntries(profiles.map((profile) => [profile.role, profile.id]));
  const planner = byRole.planner ?? profiles[0]?.id;
  if (!planner) {
    return null;
  }
  return {
    planner,
    coder: byRole.coder ?? planner,
    reviewer: byRole.reviewer ?? planner,
    embedding: byRole.embedding ?? planner,
  };
}
