// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export interface ChatSession {
  id: string;
  title: string;
  repositoryId: string | null;
  updatedAt: string;
}

export interface ChatImagePayload {
  mime: string;
  data: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName: string | null;
  toolStatus: string | null;
  previewUrls?: string[] | undefined;
}

export interface ChatClient {
  listSessions(): Promise<ChatSession[]>;
  createSession(input?: { repositoryId?: string | null }): Promise<ChatSession>;
  getSession(id: string): Promise<{ session: ChatSession; messages: ChatMessage[] }>;
  sendMessage(
    id: string,
    content: string,
    repositoryId?: string | null,
    images?: readonly ChatImagePayload[] | undefined,
  ): Promise<{ messages: ChatMessage[] }>;
  cancelTurn(id: string): Promise<void>;
  getImage(sessionId: string, imageId: string): Promise<ChatImagePayload>;
}

export function createProductionChatClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): ChatClient {
  return {
    async listSessions() {
      const payload = await jsonRequest(request, "GET", "/chat/sessions");
      const items = Array.isArray(payload.sessions) ? payload.sessions : [];
      return items.map(mapSession);
    },
    async createSession(input) {
      const payload = await jsonRequest(request, "POST", "/chat/sessions", {
        repository_id: input?.repositoryId ?? null,
      });
      return mapSession(payload.session ?? payload);
    },
    async getSession(id) {
      const payload = await jsonRequest(request, "GET", `/chat/sessions/${id}`);
      const messages = Array.isArray(payload.messages) ? payload.messages : [];
      return {
        session: mapSession(payload.session ?? payload),
        messages: messages.map(mapMessage),
      };
    },
    async sendMessage(id, content, repositoryId, images) {
      const payload = await jsonRequest(request, "POST", `/chat/sessions/${id}/messages`, {
        content,
        repository_id: repositoryId ?? null,
        ...(images && images.length > 0 ? { images } : {}),
      });
      const messages = Array.isArray(payload.messages) ? payload.messages : [];
      return { messages: messages.map(mapMessage) };
    },
    async cancelTurn(id) {
      await jsonRequest(request, "POST", `/chat/sessions/${id}/cancel`, {});
    },
    async getImage(sessionId, imageId) {
      const payload = await jsonRequest(
        request,
        "GET",
        `/chat/sessions/${sessionId}/images/${imageId}`,
      );
      return {
        mime: stringField(payload, "mime"),
        data: stringField(payload, "data"),
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

function mapSession(value: unknown): ChatSession {
  const row = asRecord(value);
  return {
    id: stringField(row, "id"),
    title: stringField(row, "title") || "New chat",
    repositoryId: stringOrNull(row.repository_id),
    updatedAt: stringField(row, "updated_at"),
  };
}

function mapMessage(value: unknown): ChatMessage {
  const row = asRecord(value);
  const role = stringField(row, "role");
  return {
    id: stringField(row, "id"),
    role: role === "user" || role === "tool" ? role : "assistant",
    content: stringField(row, "content"),
    toolName: stringOrNull(row.tool_name),
    toolStatus: stringOrNull(row.tool_status),
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
