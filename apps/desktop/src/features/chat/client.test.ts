/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionChatClient } from "./client";

describe("createProductionChatClient", () => {
  it("posts chat messages without embedding secrets", async () => {
    const bodies: unknown[] = [];
    const client = createProductionChatClient(async (method, path, body) => {
      bodies.push({ method, path, body });
      if (method === "GET" && path === "/chat/sessions") {
        return { status: 200, body: JSON.stringify({ sessions: [] }) };
      }
      if (method === "POST" && path === "/chat/sessions") {
        return {
          status: 200,
          body: JSON.stringify({
            session: {
              id: "chat_1",
              title: "New chat",
              repository_id: null,
              created_at: "t",
              updated_at: "t",
            },
            messages: [],
          }),
        };
      }
      return {
        status: 200,
        body: JSON.stringify({
          messages: [
            { id: "m1", role: "user", content: "hello", tool_name: null, tool_status: null },
          ],
        }),
      };
    });
    await client.listSessions();
    const session = await client.createSession();
    await client.sendMessage(session.id, "hello");
    await client.cancelTurn(session.id);
    expect(JSON.stringify(bodies)).toContain("/chat/sessions/chat_1/cancel");
    expect(JSON.stringify(bodies)).not.toMatch(/sk-|BEGIN RSA|api_key/i);
  });
});
