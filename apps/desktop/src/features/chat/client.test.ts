/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionChatClient, type EngineStreamPayload } from "./client";

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

  it("maps conversation messages including citations and goal refs", async () => {
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
    expect(detail.messages).toEqual([
      {
        id: "msg_asst",
        role: "assistant",
        content: "add returns a+b",
        citations: [{ path: "src/math.py", startLine: 3, endLine: 5 }],
        goalRefs: ["goal_1"],
      },
    ]);
  });

  it("streams replies through engine_stream without exposing a token or engine URL", async () => {
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
              done: true,
              content: "Hi",
              citations: [{ path: "a.py", startLine: 1, endLine: 2 }],
              goalRefs: [],
            });
          }
        },
        async cancel() {},
      },
    });

    const deltas: string[] = [];
    let doneContent = "";
    await client.streamMessage("conv_1", "hello", {
      requestId: "req-1",
      onDelta: (delta) => {
        deltas.push(delta);
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
    expect(doneContent).toBe("Hi");
  });

  it("forwards cancel to engine_stream_cancel", async () => {
    const cancelled: string[] = [];
    const client = createProductionChatClient({
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

    await client.cancelStream("req-9");
    expect(cancelled).toEqual(["req-9"]);
  });
});
