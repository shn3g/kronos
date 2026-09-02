// SPDX-License-Identifier: AGPL-3.0-or-later

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { ChatPage, type ChatPageClients } from "./ChatPage";
import type { ChatStreamHandlers, ConversationDetail } from "./client";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function clients(overrides: Partial<ChatPageClients> = {}): ChatPageClients {
  return {
    listRepositories: async () => [
      {
        id: "repo_alpha",
        displayName: "alpha",
        realpath: "C:/tmp/alpha",
        origin: "https://github.com/acme/alpha.git",
        status: "active",
      },
    ],
    listConversations: async () => [
      {
        id: "conv_1",
        repositoryId: "repo_alpha",
        title: "Ask alpha",
        createdAt: "2026-09-01T12:00:00Z",
      },
    ],
    createConversation: async () => {
      throw new Error("create should not run");
    },
    getConversation: async () => ({
      conversation: {
        id: "conv_1",
        repositoryId: "repo_alpha",
        title: "Ask alpha",
        createdAt: "2026-09-01T12:00:00Z",
      },
      messages: [
        {
          id: "msg_user",
          role: "user",
          content: "What is add?",
          citations: [],
          goalRefs: [],
        },
        {
          id: "msg_asst",
          role: "assistant",
          content: "add returns a+b",
          citations: [],
          goalRefs: [],
        },
      ],
    }),
    deleteConversation: async () => {},
    streamMessage: async () => {},
    cancelStream: async () => {},
    getGoal: async () => ({ id: "goal_1", state: "draft", title: "Fix add" }),
    ...overrides,
  };
}

describe("ChatPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const listConversations = vi.fn(async () => []);
    render(
      <ChatPage engineClient={engine("unavailable")} chatClient={clients({ listConversations })} />,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Chat" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to chat with the orchestrator/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^send$/i })).not.toBeInTheDocument();
    expect(listConversations).not.toHaveBeenCalled();
  });

  it("lists conversations when the engine is ready", async () => {
    const listConversations = vi.fn(async () => [
      {
        id: "conv_1",
        repositoryId: "repo_alpha",
        title: "Ask alpha",
        createdAt: "2026-09-01T12:00:00Z",
      },
    ]);
    render(
      <ChatPage engineClient={engine("ready")} chatClient={clients({ listConversations })} />,
    );

    expect(await screen.findByText("Ask alpha")).toBeInTheDocument();
    expect(listConversations).toHaveBeenCalledWith("repo_alpha");
    expect(await screen.findByText("What is add?")).toBeInTheDocument();
    expect(screen.getByText("add returns a+b")).toBeInTheDocument();
  });

  it("sends a message, shows streamed deltas, a citation chip, and a goal card", async () => {
    const user = userEvent.setup();
    const streamMessage = vi.fn(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
      handlers.onDelta("Here is ");
      handlers.onDelta("the patch:\n\n```ts\nconst x = 1;\n```");
      handlers.onDone({
        content: "Here is the patch:\n\n```ts\nconst x = 1;\n```",
        citations: [{ path: "src/math.py", startLine: 3, endLine: 5 }],
        goalRefs: ["goal_1"],
      });
    });
    const getGoal = vi.fn(async (id: string) => ({
      id,
      state: "planned",
      title: "Fix add",
    }));
    render(
      <ChatPage
        engineClient={engine("ready")}
        chatClient={clients({ streamMessage, getGoal })}
      />,
    );

    await screen.findByText("Ask alpha");
    await user.type(screen.getByLabelText(/message/i), "fix add");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(streamMessage).toHaveBeenCalled();
    expect(streamMessage.mock.calls[0]?.[0]).toBe("conv_1");
    expect(streamMessage.mock.calls[0]?.[1]).toBe("fix add");
    expect(await screen.findByText(/here is the patch/i)).toBeInTheDocument();
    expect(screen.getByText("src/math.py:3")).toBeInTheDocument();
    expect(await screen.findByText("goal_1")).toBeInTheDocument();
    expect(await screen.findByText(/planned/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /goals/i })).toHaveAttribute("href", "#/goals");
    expect(screen.getByRole("button", { name: /^copy$/i })).toBeInTheDocument();
    expect(getGoal).toHaveBeenCalledWith("goal_1");
  });

  it("stop calls cancel while a reply is streaming", async () => {
    const user = userEvent.setup();
    let resolveStream: () => void = () => {};
    const cancelStream = vi.fn(async () => {
      resolveStream();
    });
    const streamMessage = vi.fn((_id: string, _content: string, handlers: ChatStreamHandlers) => {
      handlers.onDelta("Thinking");
      return new Promise<void>((resolve) => {
        resolveStream = resolve;
      });
    });
    render(
      <ChatPage
        engineClient={engine("ready")}
        chatClient={clients({ streamMessage, cancelStream })}
      />,
    );

    await screen.findByText("Ask alpha");
    await user.type(screen.getByLabelText(/message/i), "Hello");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(await screen.findByText("Thinking")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^stop$/i }));
    expect(cancelStream).toHaveBeenCalled();
  });

  it("keeps optimistic and streamed messages when a late conversation load resolves", async () => {
    const user = userEvent.setup();
    let resolveLoad: (detail: ConversationDetail) => void = () => {};
    const getConversation = vi.fn(
      () =>
        new Promise<ConversationDetail>((resolve) => {
          resolveLoad = resolve;
        }),
    );
    let finishStream: () => void = () => {};
    const streamMessage = vi.fn((_id: string, _content: string, handlers: ChatStreamHandlers) => {
      handlers.onDelta("Streamed hello");
      return new Promise<void>((resolve) => {
        finishStream = () => {
          handlers.onDone({
            content: "Streamed hello",
            citations: [],
            goalRefs: [],
          });
          resolve();
        };
      });
    });
    render(
      <ChatPage
        engineClient={engine("ready")}
        chatClient={clients({ getConversation, streamMessage })}
      />,
    );

    await screen.findByText("Ask alpha");
    await user.type(screen.getByLabelText(/message/i), "Hello now");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(await screen.findByText("Hello now")).toBeInTheDocument();
    expect(await screen.findByText("Streamed hello")).toBeInTheDocument();

    await act(async () => {
      resolveLoad({
        conversation: {
          id: "conv_1",
          repositoryId: "repo_alpha",
          title: "Ask alpha",
          createdAt: "2026-09-01T12:00:00Z",
        },
        messages: [
          {
            id: "msg_user",
            role: "user",
            content: "What is add?",
            citations: [],
            goalRefs: [],
          },
          {
            id: "msg_asst",
            role: "assistant",
            content: "add returns a+b",
            citations: [],
            goalRefs: [],
          },
        ],
      });
    });

    expect(screen.getByText("Hello now")).toBeInTheDocument();
    expect(screen.getByText("Streamed hello")).toBeInTheDocument();
    expect(screen.queryByText("What is add?")).not.toBeInTheDocument();

    await act(async () => {
      finishStream();
    });

    expect(screen.getByText("Hello now")).toBeInTheDocument();
    expect(screen.getByText("Streamed hello")).toBeInTheDocument();
    expect(screen.queryByText("What is add?")).not.toBeInTheDocument();
  });

  it("shows Models guidance when the orchestrator is not configured", async () => {
    const user = userEvent.setup();
    const streamMessage = vi.fn(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
      handlers.onError("No orchestrator model is configured. Assign a model on the Models page.");
    });
    render(
      <ChatPage engineClient={engine("ready")} chatClient={clients({ streamMessage })} />,
    );

    await screen.findByText("Ask alpha");
    await user.type(screen.getByLabelText(/message/i), "What is add?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(
      await screen.findByText(/no orchestrator model is configured/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /models/i })).toHaveAttribute(
      "href",
      "#/settings/models",
    );
  });
});
