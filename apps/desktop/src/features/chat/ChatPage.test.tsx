// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPage } from "./ChatPage";
import type { ChatClient } from "./client";

function chatClient(overrides: Partial<ChatClient> = {}): ChatClient {
  return {
    listSessions: async () => [],
    createSession: async () => ({
      id: "chat_1",
      title: "New chat",
      repositoryId: null,
      updatedAt: "t",
    }),
    getSession: async () => ({
      session: {
        id: "chat_1",
        title: "New chat",
        repositoryId: null,
        updatedAt: "t",
      },
      messages: [],
    }),
    sendMessage: async (_id, content) => ({
      messages: [
        { id: "u1", role: "user", content, toolName: null, toolStatus: null },
        {
          id: "a1",
          role: "assistant",
          content: "Staff is missing before the calendar route.",
          toolName: null,
          toolStatus: null,
        },
      ],
    }),
    cancelTurn: async () => undefined,
    ...overrides,
  };
}

describe("ChatPage", () => {
  it("shows the user message before the model returns, then tool cards and the reply", async () => {
    const user = userEvent.setup();
    let finish!: (value: {
      messages: Array<{
        id: string;
        role: "user" | "assistant" | "tool";
        content: string;
        toolName: string | null;
        toolStatus: string | null;
      }>;
    }) => void;
    const sendMessage = vi.fn(
      () =>
        new Promise<{
          messages: Array<{
            id: string;
            role: "user" | "assistant" | "tool";
            content: string;
            toolName: string | null;
            toolStatus: string | null;
          }>;
        }>((resolve) => {
          finish = resolve;
        }),
    );
    render(
      <ChatPage
        chatClient={chatClient({ sendMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "What is broken in onboarding?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(await screen.findByText(/what is broken in onboarding/i)).toBeInTheDocument();
    expect(screen.getByText(/working on this turn/i)).toBeInTheDocument();
    finish({
      messages: [
        {
          id: "u1",
          role: "user",
          content: "What is broken in onboarding?",
          toolName: null,
          toolStatus: null,
        },
        {
          id: "t1",
          role: "tool",
          content: "12 hits",
          toolName: "search_index",
          toolStatus: "ok",
        },
        {
          id: "a1",
          role: "assistant",
          content: "Staff is missing before the calendar route.",
          toolName: null,
          toolStatus: null,
        },
      ],
    });
    expect(await screen.findByText(/staff is missing/i)).toBeInTheDocument();
    expect(screen.getByText(/search index · done/i)).toBeInTheDocument();
    expect(sendMessage).toHaveBeenCalled();
  });

  it("sends stop to the engine while a turn is running", async () => {
    const user = userEvent.setup();
    const cancelTurn = vi.fn(async () => undefined);
    const getSession = vi.fn(async () => ({
      session: {
        id: "chat_1",
        title: "New chat",
        repositoryId: null,
        updatedAt: "t",
      },
      messages: [
        {
          id: "u1",
          role: "user" as const,
          content: "Go",
          toolName: null,
          toolStatus: null,
        },
        {
          id: "a1",
          role: "assistant" as const,
          content: "Stopped. Ask again when you want to continue.",
          toolName: null,
          toolStatus: null,
        },
      ],
    }));
    const sendMessage = vi.fn(
      () =>
        new Promise<{
          messages: Array<{
            id: string;
            role: "user" | "assistant" | "tool";
            content: string;
            toolName: string | null;
            toolStatus: string | null;
          }>;
        }>(() => undefined),
    );
    render(
      <ChatPage
        chatClient={chatClient({ sendMessage, cancelTurn, getSession })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Go");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await user.click(await screen.findByRole("button", { name: /^stop$/i }));
    expect(cancelTurn).toHaveBeenCalledWith("chat_1");
    expect(await screen.findByText(/stopped/i)).toBeInTheDocument();
  });
});
