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

  it("posts pasted images and loads them back for the thread", async () => {
    const bodies: unknown[] = [];
    const client = createProductionChatClient(async (method, path, body) => {
      bodies.push({ method, path, body });
      if (method === "GET" && path === "/chat/sessions/chat_1/images/img_aaa") {
        return {
          status: 200,
          body: JSON.stringify({ mime: "image/png", data: "abc" }),
        };
      }
      return {
        status: 200,
        body: JSON.stringify({
          messages: [
            {
              id: "m1",
              role: "user",
              content: "![Pasted image](kronos-image:img_aaa)",
              tool_name: null,
              tool_status: null,
            },
          ],
        }),
      };
    });

    await client.sendMessage("chat_1", "see this", null, [
      { mime: "image/png", data: "abc" },
    ]);
    const image = await client.getImage("chat_1", "img_aaa");

    expect(bodies[0]).toEqual({
      method: "POST",
      path: "/chat/sessions/chat_1/messages",
      body: {
        content: "see this",
        repository_id: null,
        images: [{ mime: "image/png", data: "abc" }],
      },
    });
    expect(image).toEqual({ mime: "image/png", data: "abc" });
  });
});
