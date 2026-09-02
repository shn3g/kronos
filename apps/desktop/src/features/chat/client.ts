// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export interface ChatCitation {
  path: string;
  startLine: number;
  endLine?: number;
}

export interface ConversationSummary {
  id: string;
  repositoryId: string;
  title: string;
  createdAt: string;
}

export type ChatRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  citations: ChatCitation[];
  goalRefs: string[];
}

export interface ConversationDetail {
  conversation: ConversationSummary;
  messages: ChatMessage[];
}

export interface GoalSnippet {
  id: string;
  state: string;
  title: string;
}

export interface ChatStreamDone {
  content: string;
  citations: ChatCitation[];
  goalRefs: string[];
}

export interface ChatStreamHandlers {
  requestId: string;
  onDelta: (delta: string) => void;
  onDone: (result: ChatStreamDone) => void;
  onError: (message: string) => void;
}

export interface EngineStreamPayload {
  requestId: string;
  delta?: string;
  done: boolean;
  error?: string;
  content?: string;
  citations?: ChatCitation[];
  goalRefs?: string[];
}

export interface EngineStreamTransport {
  listen(listener: (payload: EngineStreamPayload) => void): Promise<() => void>;
  start(args: {
    method: string;
    path: string;
    body: unknown;
    requestId: string;
  }): Promise<void>;
  cancel(requestId: string): Promise<void>;
}

export interface ChatClient {
  listConversations(repositoryId: string): Promise<ConversationSummary[]>;
  createConversation(repositoryId: string, title?: string): Promise<ConversationSummary>;
  getConversation(id: string): Promise<ConversationDetail>;
  deleteConversation(id: string): Promise<void>;
  streamMessage(
    conversationId: string,
    content: string,
    handlers: ChatStreamHandlers,
  ): Promise<void>;
  cancelStream(requestId: string): Promise<void>;
  getGoal(id: string): Promise<GoalSnippet>;
}

export function createProductionChatClient(options: {
  request?: (method: string, path: string, body?: unknown) => Promise<EngineJsonResponse>;
  stream?: EngineStreamTransport;
} = {}): ChatClient {
  const request = options.request ?? requestEngineJson;
  const stream = options.stream ?? tauriStreamTransport();
  return {
    async listConversations(repositoryId) {
      const payload = await jsonRequest(
        request,
        "GET",
        `/repositories/${repositoryId}/conversations`,
      );
      const items = Array.isArray(payload.conversations) ? payload.conversations : [];
      return items.map(mapConversation);
    },
    async createConversation(repositoryId, title) {
      const payload = await jsonRequest(
        request,
        "POST",
        `/repositories/${repositoryId}/conversations`,
        { title: title ?? "New conversation" },
      );
      return mapConversation(payload);
    },
    async getConversation(id) {
      const payload = await jsonRequest(request, "GET", `/conversations/${id}`);
      const messages = Array.isArray(payload.messages) ? payload.messages : [];
      return {
        conversation: mapConversation(asRecord(payload.conversation)),
        messages: messages.map(mapMessage),
      };
    },
    async deleteConversation(id) {
      await jsonRequest(request, "DELETE", `/conversations/${id}`);
    },
    async streamMessage(conversationId, content, handlers) {
      const unlisten = await stream.listen((payload) => {
        if (payload.requestId !== handlers.requestId) {
          return;
        }
        if (payload.delta) {
          handlers.onDelta(payload.delta);
        }
        if (payload.error) {
          handlers.onError(payload.error);
          return;
        }
        if (payload.done) {
          handlers.onDone({
            content: payload.content ?? "",
            citations: payload.citations ?? [],
            goalRefs: payload.goalRefs ?? [],
          });
        }
      });
      try {
        await stream.start({
          method: "POST",
          path: `/conversations/${conversationId}/messages`,
          body: { content },
          requestId: handlers.requestId,
        });
      } catch {
        handlers.onError("Could not stream the orchestrator reply.");
      } finally {
        unlisten();
      }
    },
    async cancelStream(requestId) {
      await stream.cancel(requestId);
    },
    async getGoal(id) {
      const payload = await jsonRequest(request, "GET", `/goals/${id}`);
      const goal = asRecord(payload.goal);
      return {
        id: stringField(goal, "id") || id,
        state: stringField(goal, "state"),
        title: stringField(goal, "title"),
      };
    },
  };
}

function tauriStreamTransport(): EngineStreamTransport {
  return {
    async listen(listener) {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        const unlisten = await listen<EngineStreamPayload>("engine-stream", (event) => {
          listener(event.payload);
        });
        return unlisten;
      } catch {
        return () => {};
      }
    },
    async start(args) {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("engine_stream", {
        method: args.method,
        path: args.path,
        body: args.body,
        requestId: args.requestId,
      });
    },
    async cancel(requestId) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("engine_stream_cancel", { requestId });
      } catch {
        return;
      }
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

function mapConversation(raw: unknown): ConversationSummary {
  const item = asRecord(raw);
  return {
    id: stringField(item, "id"),
    repositoryId: stringField(item, "repository_id"),
    title: stringField(item, "title"),
    createdAt: stringField(item, "created_at"),
  };
}

function mapMessage(raw: unknown): ChatMessage {
  const item = asRecord(raw);
  const citations = Array.isArray(item.citations) ? item.citations : [];
  const goalRefs = Array.isArray(item.goal_refs)
    ? item.goal_refs
    : Array.isArray(item.goalRefs)
      ? item.goalRefs
      : [];
  return {
    id: stringField(item, "id"),
    role: parseRole(item.role),
    content: stringField(item, "content"),
    citations: citations.map(mapCitation),
    goalRefs: goalRefs.filter((value): value is string => typeof value === "string"),
  };
}

function mapCitation(raw: unknown): ChatCitation {
  const item = asRecord(raw);
  const start = item.start_line ?? item.startLine;
  const end = item.end_line ?? item.endLine;
  return {
    path: stringField(item, "path"),
    startLine: typeof start === "number" ? start : 0,
    ...(typeof end === "number" ? { endLine: end } : {}),
  };
}

function parseRole(value: unknown): ChatRole {
  if (value === "user" || value === "assistant" || value === "system") {
    return value;
  }
  return "assistant";
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
