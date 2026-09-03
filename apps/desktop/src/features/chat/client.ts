// SPDX-License-Identifier: AGPL-3.0-or-later

import { DESKTOP_CLIENT_VERSION } from "../../api/kronosClient";
import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export interface ChatCitation {
  path: string;
  startLine: number;
  endLine?: number;
}

export interface ConversationSummary {
  id: string;
  repositoryId: string | null;
  title: string;
  createdAt: string;
}

export type ChatRole = "user" | "assistant" | "system" | "tool";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  citations: ChatCitation[];
  goalRefs: string[];
  toolName: string | null;
  toolStatus: string | null;
  toolJson: string | null;
  previewUrls?: string[];
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

export interface ChatImagePayload {
  mime: string;
  data: string;
}

export interface ChatReadinessCheck {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
}

export interface ChatToolEvent {
  id: string;
  name: string;
  status: string;
  args?: Record<string, unknown>;
  summary?: string;
  output?: string;
}

export interface ChatGoalEvent {
  id: string;
  state: string;
  canExecute: boolean;
  readiness: ChatReadinessCheck[];
}

export interface ChatStreamDone {
  content: string;
  citations: ChatCitation[];
  goalRefs: string[];
}

export interface ChatStreamHandlers {
  requestId: string;
  images?: readonly ChatImagePayload[];
  onDelta: (delta: string) => void;
  onTool?: (tool: ChatToolEvent) => void;
  onGoal?: (goal: ChatGoalEvent) => void;
  onDone: (result: ChatStreamDone) => void;
  onError: (message: string) => void;
}

export interface EngineStreamPayload {
  requestId?: string;
  delta?: string;
  done: boolean;
  error?: string;
  content?: string;
  citations?: ChatCitation[];
  goalRefs?: string[];
  tool?: unknown;
  goal?: unknown;
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
  listConversations(repositoryId: string | null): Promise<ConversationSummary[]>;
  createConversation(repositoryId: string | null, title?: string): Promise<ConversationSummary>;
  getConversation(id: string): Promise<ConversationDetail>;
  deleteConversation(id: string): Promise<void>;
  streamMessage(
    conversationId: string,
    content: string,
    handlers: ChatStreamHandlers,
  ): Promise<void>;
  cancelStream(conversationId: string, requestId: string): Promise<void>;
  getGoal(id: string): Promise<GoalSnippet>;
  getImage(conversationId: string, imageId: string): Promise<ChatImagePayload>;
}

const WEB_ENGINE_BASE = "/kronos-engine";

export function createProductionChatClient(options: {
  request?: (method: string, path: string, body?: unknown) => Promise<EngineJsonResponse>;
  stream?: EngineStreamTransport;
  fetchImpl?: typeof fetch;
  webBase?: string;
} = {}): ChatClient {
  const request = options.request ?? requestEngineJson;
  const stream = options.stream ?? tauriStreamTransport();
  const fetchImpl = options.fetchImpl ?? fetch;
  const webBase = (options.webBase ?? WEB_ENGINE_BASE).replace(/\/$/, "");
  const abortByRequest = new Map<string, AbortController>();
  return {
    async listConversations(repositoryId) {
      const path =
        repositoryId === null
          ? "/conversations"
          : `/repositories/${repositoryId}/conversations`;
      const payload = await jsonRequest(request, "GET", path);
      const items = Array.isArray(payload.conversations) ? payload.conversations : [];
      return items.map(mapConversation);
    },
    async createConversation(repositoryId, title) {
      const conversationTitle = title ?? "New conversation";
      if (repositoryId === null) {
        const payload = await jsonRequest(request, "POST", "/conversations", {
          repository_id: null,
          title: conversationTitle,
        });
        return mapConversation(payload);
      }
      const payload = await jsonRequest(
        request,
        "POST",
        `/repositories/${repositoryId}/conversations`,
        { title: conversationTitle },
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
      const body: Record<string, unknown> = { content };
      if (handlers.images && handlers.images.length > 0) {
        body.images = handlers.images;
      }
      const args = {
        method: "POST",
        path: `/conversations/${conversationId}/messages`,
        body,
        requestId: handlers.requestId,
      };
      const unlisten = await stream.listen((payload) => {
        if (payload.requestId && payload.requestId !== handlers.requestId) {
          return;
        }
        dispatchStreamPayload(payload, handlers);
      });
      try {
        try {
          await stream.start(args);
        } catch {
          await fetchSseFallback(fetchImpl, webBase, args, handlers, abortByRequest);
        }
      } finally {
        unlisten();
        abortByRequest.delete(handlers.requestId);
      }
    },
    async cancelStream(conversationId, requestId) {
      abortByRequest.get(requestId)?.abort();
      abortByRequest.delete(requestId);
      await stream.cancel(requestId);
      await jsonRequest(request, "POST", `/conversations/${conversationId}/cancel`, {});
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
    async getImage(conversationId, imageId) {
      const payload = await jsonRequest(
        request,
        "GET",
        `/conversations/${conversationId}/images/${imageId}`,
      );
      return {
        mime: stringField(payload, "mime"),
        data: stringField(payload, "data"),
      };
    },
  };
}

export function parseEngineSseDataLine(line: string): EngineStreamPayload | null {
  const trimmed = line.trimEnd().replace(/\r$/, "");
  if (!trimmed.startsWith("data:")) {
    return null;
  }
  const data = trimmed.slice(5).trim();
  if (data === "" || data === "[DONE]") {
    return null;
  }
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  const record = asRecord(value);
  if (typeof record.tool !== "undefined") {
    return { done: false, tool: record.tool };
  }
  if (typeof record.goal !== "undefined") {
    return { done: false, goal: record.goal };
  }
  if (typeof record.error === "string") {
    return { done: true, error: record.error };
  }
  const done = record.done === true || (typeof record.content === "string" && "citations" in record);
  if (done) {
    const citations = Array.isArray(record.citations) ? record.citations : [];
    const goalRefs = Array.isArray(record.goal_refs)
      ? record.goal_refs
      : Array.isArray(record.goalRefs)
        ? record.goalRefs
        : [];
    return {
      done: true,
      content: typeof record.content === "string" ? record.content : "",
      citations: citations.map(mapCitation),
      goalRefs: goalRefs.filter((item): item is string => typeof item === "string"),
    };
  }
  if (typeof record.delta === "string") {
    return { done: false, delta: record.delta };
  }
  return null;
}

function dispatchStreamPayload(payload: EngineStreamPayload, handlers: ChatStreamHandlers): void {
  if (payload.delta) {
    handlers.onDelta(payload.delta);
  }
  if (typeof payload.tool !== "undefined") {
    handlers.onTool?.(mapToolEvent(payload.tool));
  }
  if (typeof payload.goal !== "undefined") {
    handlers.onGoal?.(mapGoalEvent(payload.goal));
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
}

async function fetchSseFallback(
  fetchImpl: typeof fetch,
  webBase: string,
  args: { method: string; path: string; body: unknown; requestId: string },
  handlers: ChatStreamHandlers,
  abortByRequest: Map<string, AbortController>,
): Promise<void> {
  const controller = new AbortController();
  abortByRequest.set(args.requestId, controller);
  let response: Response;
  try {
    response = await fetchImpl(`${webBase}${args.path}`, {
      method: args.method,
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        "X-Kronos-Client-Version": DESKTOP_CLIENT_VERSION,
      },
      body: JSON.stringify(args.body),
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) {
      return;
    }
    handlers.onError("Could not stream the orchestrator reply.");
    return;
  }
  if (!response.ok) {
    handlers.onError("Could not stream the orchestrator reply.");
    return;
  }
  const streamBody = response.body;
  if (!streamBody) {
    const text = await response.text();
    dispatchSseBuffer(text, handlers);
    return;
  }
  const reader = streamBody.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) {
        buffer += decoder.decode();
        dispatchSseBuffer(buffer, handlers);
        break;
      }
      buffer += decoder.decode(next.value, { stream: true });
      const split = splitSseBuffer(buffer);
      buffer = split.rest;
      for (const line of split.lines) {
        const payload = parseEngineSseDataLine(line);
        if (payload) {
          dispatchStreamPayload(payload, handlers);
        }
      }
    }
  } catch {
    if (!controller.signal.aborted) {
      handlers.onError("Could not stream the orchestrator reply.");
    }
  }
}

function splitSseBuffer(buffer: string): { lines: string[]; rest: string } {
  const lines: string[] = [];
  let rest = buffer;
  while (true) {
    const index = rest.indexOf("\n");
    if (index === -1) {
      break;
    }
    lines.push(rest.slice(0, index));
    rest = rest.slice(index + 1);
  }
  return { lines, rest };
}

function dispatchSseBuffer(buffer: string, handlers: ChatStreamHandlers): void {
  const split = splitSseBuffer(buffer.endsWith("\n") ? buffer : `${buffer}\n`);
  for (const line of split.lines) {
    const payload = parseEngineSseDataLine(line);
    if (payload) {
      dispatchStreamPayload(payload, handlers);
    }
  }
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
      const { invoke, isTauri } = await import("@tauri-apps/api/core");
      if (!isTauri()) {
        throw new Error("not in tauri");
      }
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
    repositoryId: stringOrNull(item.repository_id),
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
    toolName: stringOrNull(item.tool_name),
    toolStatus: stringOrNull(item.tool_status),
    toolJson: stringOrNull(item.tool_json),
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

function mapToolEvent(raw: unknown): ChatToolEvent {
  const item = asRecord(raw);
  const args = asRecord(item.args);
  return {
    id: stringField(item, "id"),
    name: stringField(item, "name"),
    status: stringField(item, "status"),
    ...(Object.keys(args).length > 0 ? { args } : {}),
    ...(typeof item.summary === "string" ? { summary: item.summary } : {}),
    ...(typeof item.output === "string" ? { output: item.output } : {}),
  };
}

function mapGoalEvent(raw: unknown): ChatGoalEvent {
  const item = asRecord(raw);
  const readinessRaw = Array.isArray(item.readiness) ? item.readiness : [];
  return {
    id: stringField(item, "id"),
    state: stringField(item, "state"),
    canExecute: item.can_execute === true || item.canExecute === true,
    readiness: readinessRaw.map((row) => {
      const check = asRecord(row);
      return {
        id: stringField(check, "id"),
        label: stringField(check, "label"),
        ok: check.ok === true,
        detail: stringField(check, "detail"),
      };
    }),
  };
}

function parseRole(value: unknown): ChatRole {
  if (value === "user" || value === "assistant" || value === "system" || value === "tool") {
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

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
