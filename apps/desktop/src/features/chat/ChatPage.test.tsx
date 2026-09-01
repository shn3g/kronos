// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPage } from "./ChatPage";
import type { ChatClient } from "./client";
import type { IndexClient } from "../index/client";

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

function indexClient(search: IndexClient["search"]): IndexClient {
  return {
    status: async () => ({
      repositoryId: "repo_alpha",
      commit: "abc",
      chunkCount: 4,
      denseAvailable: false,
      indexPath: "/tmp/index",
      ready: true,
    }),
    rebuild: async () => ({
      repositoryId: "repo_alpha",
      commit: "abc",
      chunkCount: 4,
      denseAvailable: false,
      indexPath: "/tmp/index",
      ready: true,
    }),
    search,
  };
}

describe("ChatPage", () => {
  it("names the assigned model in the composer", async () => {
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        plannerName="Local llama"
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByText("Local llama")).toBeInTheDocument();
  });

  it("opens models when the composer model name is chosen", async () => {
    const user = userEvent.setup();
    const onOpenModels = vi.fn();
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        plannerName="Local llama"
        onOpenWorkspace={() => undefined}
        onOpenModels={onOpenModels}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Local llama" }));
    expect(onOpenModels).toHaveBeenCalled();
  });

  it("keeps Send disabled until the composer has text", async () => {
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("button", { name: /^send$/i })).toBeDisabled();
  });

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

  it("shows streamed assistant text while send is still in flight", async () => {
    const user = userEvent.setup();
    let polls = 0;
    const getSession = vi.fn(async () => {
      polls += 1;
      const streamed =
        polls >= 2
          ? [
              {
                id: "a1",
                role: "assistant" as const,
                content: "Staff is missing",
                toolName: null,
                toolStatus: "streaming",
              },
            ]
          : [];
      return {
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
          ...streamed,
        ],
      };
    });
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
        chatClient={chatClient({ sendMessage, getSession })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Go");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(
      () => {
        expect(screen.getByText(/staff is missing/i)).toBeInTheDocument();
      },
      { timeout: 1500 },
    );
  });

  it("renders assistant markdown as bold text and a code block", async () => {
    const user = userEvent.setup();
    render(
      <ChatPage
        chatClient={chatClient({
          sendMessage: async () => ({
            messages: [
              { id: "u1", role: "user", content: "Show me", toolName: null, toolStatus: null },
              {
                id: "a1",
                role: "assistant",
                content: "Staff is **missing**.\n\n```ts\nconst ok = false;\n```\n",
                toolName: null,
                toolStatus: null,
              },
            ],
          }),
        })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Show me");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(await screen.findByText("missing")).toBeInTheDocument();
    expect(screen.getByText("missing").tagName).toBe("STRONG");
    expect(screen.getByText("const ok = false;")).toBeInTheDocument();
  });

  it("inserts an indexed file path when an @ mention is chosen", async () => {
    const user = userEvent.setup();
    const search = vi.fn(async () => [
      {
        path: "src/App.tsx",
        startLine: 1,
        endLine: 20,
        commit: "abc",
        symbol: null,
        rankSources: ["fts"],
        trust: "ok",
        text: "export function App",
      },
    ]);
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        indexClient={indexClient(search)}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @app");
    await user.click(await screen.findByRole("option", { name: "src/App.tsx" }));
    expect(box).toHaveValue("Fix @src/App.tsx ");
    expect(search).toHaveBeenCalledWith("repo_alpha", "app");
  });

  it("inserts the first mention on Enter instead of sending", async () => {
    const user = userEvent.setup();
    const sendMessage = vi.fn();
    const search = vi.fn(async () => [
      {
        path: "src/App.tsx",
        startLine: 1,
        endLine: 20,
        commit: "abc",
        symbol: null,
        rankSources: ["fts"],
        trust: "ok",
        text: "export function App",
      },
    ]);
    render(
      <ChatPage
        chatClient={chatClient({ sendMessage })}
        repositoryId="repo_alpha"
        historyOpen={false}
        indexClient={indexClient(search)}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @app");
    await screen.findByRole("option", { name: "src/App.tsx" });
    await user.keyboard("{Enter}");
    expect(box).toHaveValue("Fix @src/App.tsx ");
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("moves the mention highlight with arrow keys before inserting", async () => {
    const user = userEvent.setup();
    const search = vi.fn(async () => [
      {
        path: "src/App.tsx",
        startLine: 1,
        endLine: 20,
        commit: "abc",
        symbol: null,
        rankSources: ["fts"],
        trust: "ok",
        text: "export function App",
      },
      {
        path: "src/main.tsx",
        startLine: 1,
        endLine: 10,
        commit: "abc",
        symbol: null,
        rankSources: ["fts"],
        trust: "ok",
        text: "import App",
      },
    ]);
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        indexClient={indexClient(search)}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @ap");
    await screen.findByRole("option", { name: "src/main.tsx" });
    await user.keyboard("{ArrowDown}{Enter}");
    expect(box).toHaveValue("Fix @src/main.tsx ");
  });
});
