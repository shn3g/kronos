/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { DESKTOP_CLIENT_VERSION } from "../../api/kronosClient";
import {
  createProductionChatClient,
  parseEngineSseDataLine,
  type EngineStreamPayload,
} from "./client";

describe("parseEngineSseDataLine", () => {
  it("parses delta, tool, goal, error, and done payloads", () => {
    expect(parseEngineSseDataLine('data: {"delta":"Hi"}')).toEqual({
      delta: "Hi",
      done: false,
    });
    expect(
      parseEngineSseDataLine(
        'data: {"tool":{"id":"t1","name":"read_file","status":"running","args":{"path":"a.ts"}}}',
      ),
    ).toEqual({
      tool: { id: "t1", name: "read_file", status: "running", args: { path: "a.ts" } },
      done: false,
    });
    expect(
      parseEngineSseDataLine(
        'data: {"goal":{"id":"goal_x","state":"draft","can_execute":false,"readiness":[]}}',
      ),
    ).toEqual({
      goal: { id: "goal_x", state: "draft", can_execute: false, readiness: [] },
      done: false,
    });
    expect(parseEngineSseDataLine('data: {"error":"The model stopped."}')).toEqual({
      error: "The model stopped.",
      done: true,
    });
    expect(
      parseEngineSseDataLine(
        'data: {"content":"Hi","citations":[{"path":"a.py","start_line":1}],"goal_refs":["goal_x"],"done":true}',
      ),
    ).toEqual({
      done: true,
      content: "Hi",
      citations: [{ path: "a.py", startLine: 1 }],
      goalRefs: ["goal_x"],
    });
  });

  it("ignores blank SSE lines and [DONE]", () => {
    expect(parseEngineSseDataLine("data:")).toBeNull();
    expect(parseEngineSseDataLine("data: [DONE]")).toBeNull();
    expect(parseEngineSseDataLine(":")).toBeNull();
  });
});

describe("createProductionChatClient", () => {
  it("lists conversations through the engine JSON proxy", async () => {
    const client = createProductionChatClient({
      request: async (method, path) => {
        expect(method).toBe("GET");
        expect(path).toBe("/repositories/repo_alpha/conversations");
        return {
          status: 200,
          body: JSON.stringify({
            conversations: [
              {
                id: "conv_1",
                repository_id: "repo_alpha",
                title: "Ask alpha",
                created_at: "2026-09-01T12:00:00Z",
              },
            ],
          }),
        };
      },
    });

    await expect(client.listConversations("repo_alpha")).resolves.toEqual([
      {
        id: "conv_1",
        repositoryId: "repo_alpha",
        title: "Ask alpha",
        createdAt: "2026-09-01T12:00:00Z",
      },
    ]);
  });

  it("lists and creates no-workspace conversations on /conversations", async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    const client = createProductionChatClient({
      request: async (method, path, body) => {
        calls.push({ method, path, body });
        if (method === "GET") {
          return {
            status: 200,
            body: JSON.stringify({
              conversations: [
                {
                  id: "conv_loose",
                  repository_id: null,
                  title: "Loose",
                  created_at: "2026-09-01T12:00:00Z",
                },
              ],
            }),
          };
        }
        return {
          status: 200,
          body: JSON.stringify({
            id: "conv_new",
            repository_id: null,
            title: "New conversation",
            created_at: "2026-09-01T12:00:00Z",
          }),
        };
      },
    });

    await expect(client.listConversations(null)).resolves.toEqual([
      {
        id: "conv_loose",
        repositoryId: null,
        title: "Loose",
        createdAt: "2026-09-01T12:00:00Z",
      },
    ]);
    await expect(client.createConversation(null, "Loose chat")).resolves.toEqual({
      id: "conv_new",
      repositoryId: null,
      title: "New conversation",
      createdAt: "2026-09-01T12:00:00Z",
    });

    expect(calls).toEqual([
      { method: "GET", path: "/conversations", body: undefined },
      {
        method: "POST",
        path: "/conversations",
        body: { repository_id: null, title: "Loose chat" },
      },
    ]);
    expect(JSON.stringify(calls)).not.toMatch(/\/chat\/sessions/);
  });

  it("maps conversation messages including tool rows, citations, and goal refs", async () => {
    const client = createProductionChatClient({
      request: async (method, path) => {
        expect(method).toBe("GET");
        expect(path).toBe("/conversations/conv_1");
        return {
          status: 200,
          body: JSON.stringify({
            conversation: {
              id: "conv_1",
              repository_id: "repo_alpha",
              title: "Ask alpha",
              created_at: "2026-09-01T12:00:00Z",
            },
            messages: [
              {
                id: "msg_tool",
                role: "tool",
                content: "Read 12 lines",
                citations: [],
                goal_refs: [],
                tool_name: "read_file",
                tool_status: "ok",
                tool_json: '{"summary":"Read 12 lines","output":"const x = 1"}',
                created_at: "2026-09-01T12:01:00Z",
              },
              {
                id: "msg_asst",
                role: "assistant",
                content: "add returns a+b",
                citations: [{ path: "src/math.py", start_line: 3, end_line: 5 }],
                goal_refs: ["goal_1"],
                created_at: "2026-09-01T12:01:00Z",
              },
            ],
          }),
        };
      },
    });

    const detail = await client.getConversation("conv_1");
    expect(detail.conversation.repositoryId).toBe("repo_alpha");
    expect(detail.messages).toEqual([
      {
        id: "msg_tool",
        role: "tool",
        content: "Read 12 lines",
        citations: [],
        goalRefs: [],
        toolName: "read_file",
        toolStatus: "ok",
        toolJson: '{"summary":"Read 12 lines","output":"const x = 1"}',
      },
      {
        id: "msg_asst",
        role: "assistant",
        content: "add returns a+b",
        citations: [{ path: "src/math.py", startLine: 3, endLine: 5 }],
        goalRefs: ["goal_1"],
        toolName: null,
        toolStatus: null,
        toolJson: null,
      },
    ]);
  });

  it("streams replies through engine_stream including tool and goal payloads", async () => {
    const listeners: Array<(payload: EngineStreamPayload) => void> = [];
    const started: unknown[] = [];
    const client = createProductionChatClient({
      stream: {
        async listen(listener) {
          listeners.push(listener);
          return () => {};
        },
        async start(args) {
          started.push(args);
          for (const listener of listeners) {
            listener({ requestId: args.requestId, delta: "Hi", done: false });
            listener({
              requestId: args.requestId,
              done: false,
              tool: { id: "t1", name: "read_file", status: "ok", summary: "Read 2 lines" },
            });
            listener({
              requestId: args.requestId,
              done: false,
              goal: {
                id: "goal_x",
                state: "draft",
                can_execute: false,
                readiness: [{ id: "workspace_active", label: "Workspace", ok: true, detail: "ok" }],
              },
            });
            listener({
              requestId: args.requestId,
              done: true,
              content: "Hi",
              citations: [{ path: "a.py", startLine: 1, endLine: 2 }],
              goalRefs: ["goal_x"],
            });
          }
        },
        async cancel() {},
      },
    });

    const deltas: string[] = [];
    const tools: unknown[] = [];
    const goals: unknown[] = [];
    let doneContent = "";
    await client.streamMessage("conv_1", "hello", {
      requestId: "req-1",
      onDelta: (delta) => {
        deltas.push(delta);
      },
      onTool: (tool) => {
        tools.push(tool);
      },
      onGoal: (goal) => {
        goals.push(goal);
      },
      onDone: (result) => {
        doneContent = result.content;
      },
      onError: () => {
        throw new Error("should not error");
      },
    });

    expect(started).toEqual([
      {
        method: "POST",
        path: "/conversations/conv_1/messages",
        body: { content: "hello" },
        requestId: "req-1",
      },
    ]);
    expect(JSON.stringify(started)).not.toMatch(/Bearer|127\.0\.0\.1|auth_token|localhost/i);
    expect(deltas).toEqual(["Hi"]);
    expect(tools).toEqual([{ id: "t1", name: "read_file", status: "ok", summary: "Read 2 lines" }]);
    expect(goals).toEqual([
      {
        id: "goal_x",
        state: "draft",
        canExecute: false,
        readiness: [{ id: "workspace_active", label: "Workspace", ok: true, detail: "ok" }],
      },
    ]);
    expect(doneContent).toBe("Hi");
  });

  it("posts pasted images on the stream body", async () => {
    const started: unknown[] = [];
    const client = createProductionChatClient({
      stream: {
        async listen() {
          return () => {};
        },
        async start(args) {
          started.push(args);
        },
        async cancel() {},
      },
    });

    await client.streamMessage("conv_1", "see this", {
      requestId: "req-img",
      images: [{ mime: "image/png", data: "abc" }],
      onDelta: () => undefined,
      onDone: () => undefined,
      onError: () => undefined,
    });

    expect(started).toEqual([
      {
        method: "POST",
        path: "/conversations/conv_1/messages",
        body: { content: "see this", images: [{ mime: "image/png", data: "abc" }] },
        requestId: "req-img",
      },
    ]);
  });

  it("falls back to fetch SSE when Tauri engine_stream fails", async () => {
    const sse = [
      `data: ${JSON.stringify({ delta: "Hi" })}\n\n`,
      `data: ${JSON.stringify({ tool: { id: "t1", name: "read_file", status: "running" } })}\n\n`,
      `data: ${JSON.stringify({
        tool: { id: "t1", name: "read_file", status: "ok", summary: "Read 2 lines", output: "ok" },
      })}\n\n`,
      `data: ${JSON.stringify({
        goal: {
          id: "goal_x",
          state: "draft",
          can_execute: false,
          readiness: [{ id: "models_assigned", label: "Models", ok: false, detail: "Assign models" }],
        },
      })}\n\n`,
      `data: ${JSON.stringify({
        content: "Hi",
        citations: [{ path: "a.py", start_line: 1 }],
        goal_refs: ["goal_x"],
        done: true,
      })}\n\n`,
    ].join("");
    const fetches: Array<{ url: string; init: RequestInit }> = [];
    const client = createProductionChatClient({
      stream: {
        async listen() {
          return () => {};
        },
        async start() {
          throw new Error("not in tauri");
        },
        async cancel() {},
      },
      fetchImpl: async (input, init) => {
        fetches.push({ url: String(input), init: init ?? {} });
        return new Response(sse, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      },
    });

    const deltas: string[] = [];
    const tools: Array<{ status: string }> = [];
    const goals: Array<{ id: string; canExecute: boolean }> = [];
    let doneContent = "";
    await client.streamMessage("conv_1", "hello", {
      requestId: "req-web",
      onDelta: (delta) => {
        deltas.push(delta);
      },
      onTool: (tool) => {
        tools.push({ status: tool.status });
      },
      onGoal: (goal) => {
        goals.push({ id: goal.id, canExecute: goal.canExecute });
      },
      onDone: (result) => {
        doneContent = result.content;
        expect(result.citations).toEqual([{ path: "a.py", startLine: 1 }]);
        expect(result.goalRefs).toEqual(["goal_x"]);
      },
      onError: () => {
        throw new Error("should not error");
      },
    });

    expect(fetches).toHaveLength(1);
    expect(fetches[0]?.url).toBe("/kronos-engine/conversations/conv_1/messages");
    const headers = new Headers(fetches[0]?.init.headers);
    expect(headers.get("Accept")).toBe("text/event-stream");
    expect(headers.get("X-Kronos-Client-Version")).toBe(DESKTOP_CLIENT_VERSION);
    expect(headers.get("Authorization")).toBeNull();
    expect(JSON.stringify(fetches)).not.toMatch(/Bearer|auth_token/i);
    expect(deltas).toEqual(["Hi"]);
    expect(tools.map((item) => item.status)).toEqual(["running", "ok"]);
    expect(goals).toEqual([{ id: "goal_x", canExecute: false }]);
    expect(doneContent).toBe("Hi");
  });

  it("cancels both the stream and POST /conversations/{id}/cancel", async () => {
    const cancelled: string[] = [];
    const requests: Array<{ method: string; path: string; body?: unknown }> = [];
    const client = createProductionChatClient({
      request: async (method, path, body) => {
        requests.push({ method, path, body });
        return { status: 200, body: JSON.stringify({ ok: true }) };
      },
      stream: {
        async listen() {
          return () => {};
        },
        async start() {},
        async cancel(requestId) {
          cancelled.push(requestId);
        },
      },
    });

    await client.cancelStream("conv_1", "req-9");
    expect(cancelled).toEqual(["req-9"]);
    expect(requests).toEqual([
      { method: "POST", path: "/conversations/conv_1/cancel", body: {} },
    ]);
  });

  it("loads a pasted image from GET /conversations/{id}/images/{imageId}", async () => {
    const client = createProductionChatClient({
      request: async (method, path) => {
        expect(method).toBe("GET");
        expect(path).toBe("/conversations/conv_1/images/img_aaa");
        return { status: 200, body: JSON.stringify({ mime: "image/png", data: "abc" }) };
      },
    });

    await expect(client.getImage("conv_1", "img_aaa")).resolves.toEqual({
      mime: "image/png",
      data: "abc",
    });
  });
});
