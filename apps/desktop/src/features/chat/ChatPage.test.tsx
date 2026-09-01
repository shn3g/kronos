// SPDX-License-Identifier: AGPL-3.0-or-later

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    getImage: async () => ({ mime: "image/png", data: "" }),
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
    expect(screen.getByRole("progressbar", { name: /about \d+ of 32000 tokens/i })).toBeInTheDocument();
  });

  it("says workspace instruction files are followed when a folder is open", async () => {
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(
      await screen.findByText(/AGENTS.md and Cursor rules files in this folder are followed/i),
    ).toBeInTheDocument();
  });

  it("warns when the loaded thread is near the context window", async () => {
    render(
      <ChatPage
        chatClient={chatClient({
          listSessions: async () => [
            {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              updatedAt: "t",
            },
          ],
          getSession: async () => ({
            session: {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              updatedAt: "t",
            },
            messages: [
              {
                id: "u1",
                role: "user",
                content: "x".repeat(110_000),
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

    expect(
      await screen.findByText("This chat is getting long. Start a new chat if replies get worse."),
    ).toBeInTheDocument();
  });

  it("shows run_command output as preformatted text", async () => {
    render(
      <ChatPage
        chatClient={chatClient({
          listSessions: async () => [
            {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              updatedAt: "t",
            },
          ],
          getSession: async () => ({
            session: {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              updatedAt: "t",
            },
            messages: [
              {
                id: "u1",
                role: "user",
                content: "Run the tests.",
                toolName: null,
                toolStatus: null,
              },
              {
                id: "t1",
                role: "tool",
                content: "Exit 0\n\n3 passed",
                toolName: "run_command",
                toolStatus: "ok",
              },
            ],
          }),
        })}
        repositoryId="repo_alpha"
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByText("Run command · done")).toBeInTheDocument();
    const output = screen.getByText(/3 passed/i);
    expect(output.tagName).toBe("PRE");
    expect(screen.getByRole("button", { name: /^copy output$/i })).toBeInTheDocument();
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

  it("stops the current turn when Escape is pressed", async () => {
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
    await screen.findByRole("button", { name: /^stop$/i });
    await user.keyboard("{Escape}");
    expect(cancelTurn).toHaveBeenCalledWith("chat_1");
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
    expect(screen.getByRole("button", { name: /^copy$/i })).toBeInTheDocument();
  });

  it("applies a fenced file through onApplyFile", async () => {
    const user = userEvent.setup();
    const onApplyFile = vi.fn().mockResolvedValue(undefined);
    render(
      <ChatPage
        chatClient={chatClient({
          sendMessage: async () => ({
            messages: [
              { id: "u1", role: "user", content: "Show me", toolName: null, toolStatus: null },
              {
                id: "a1",
                role: "assistant",
                content: "```ts src/ok.ts\nconst ok = false;\n```\n",
                toolName: null,
                toolStatus: null,
              },
            ],
          }),
        })}
        repositoryId="repo_alpha"
        historyOpen={false}
        onOpenWorkspace={() => undefined}
        onApplyFile={onApplyFile}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Show me");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await user.click(await screen.findByRole("button", { name: /^apply$/i }));

    expect(onApplyFile).toHaveBeenCalledWith("src/ok.ts", "const ok = false;");
  });

  it("renders @ file mentions in the user bubble as code", async () => {
    const user = userEvent.setup();
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @src/App.tsx");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    const mentioned = await screen.findAllByText("src/App.tsx");
    expect(mentioned[0]?.tagName).toBe("CODE");
    expect(screen.queryByRole("button", { name: /open src\/app\.tsx/i })).not.toBeInTheDocument();
  });

  it("opens a mentioned workspace file from the user bubble", async () => {
    const user = userEvent.setup();
    const onOpenPath = vi.fn();
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        onOpenWorkspace={() => undefined}
        onOpenPath={onOpenPath}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @src/App.tsx");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await user.click(await screen.findByRole("button", { name: /open src\/app\.tsx/i }));

    expect(onOpenPath).toHaveBeenCalledWith("src/App.tsx");
  });

  it("does not open a parent-directory mention as a file", async () => {
    const user = userEvent.setup();
    const onOpenPath = vi.fn();
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        onOpenWorkspace={() => undefined}
        onOpenPath={onOpenPath}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Ignore @../secret.txt");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(await screen.findByText("../secret.txt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open \.\.\/secret\.txt/i })).not.toBeInTheDocument();
    expect(onOpenPath).not.toHaveBeenCalled();
  });

  it("appends a workspace path from an external mention request", async () => {
    const { rerender } = render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        mentionRequest={{ path: "", nonce: 0 }}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("textbox", { name: /ask kronos/i })).toHaveValue("");
    rerender(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        mentionRequest={{ path: "src/app.py", nonce: 1 }}
        onOpenWorkspace={() => undefined}
      />,
    );
    expect(await screen.findByRole("textbox", { name: /ask kronos/i })).toHaveValue("@src/app.py ");
  });

  it("quotes selected lines from an external mention request", async () => {
    const { rerender } = render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        mentionRequest={{ path: "", nonce: 0 }}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("textbox", { name: /ask kronos/i })).toHaveValue("");
    rerender(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        mentionRequest={{
          path: "src/app.py",
          nonce: 1,
          selectedText: "def connect():",
          startLine: 2,
          endLine: 2,
        }}
        onOpenWorkspace={() => undefined}
      />,
    );
    expect(await screen.findByRole("textbox", { name: /ask kronos/i })).toHaveValue(
      "@src/app.py\n\nSelected line 2:\n```\ndef connect():\n```\n",
    );
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

  it("explains when the workspace index is still building during an @ mention", async () => {
    const user = userEvent.setup();
    const search = vi.fn(async () => []);
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        indexClient={{
          ...indexClient(search),
          status: async () => ({
            repositoryId: "repo_alpha",
            commit: null,
            chunkCount: 0,
            denseAvailable: false,
            indexPath: "/tmp/index",
            ready: false,
          }),
        }}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Look at @app");
    expect(await screen.findByText("The search index is still building.")).toBeInTheDocument();
    expect(search).toHaveBeenCalled();
  });

  it("says when no indexed files match an @ mention", async () => {
    const user = userEvent.setup();
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        indexClient={indexClient(async () => [])}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Look at @zzzz");
    expect(await screen.findByText("No matching files.")).toBeInTheDocument();
  });

  it("lets you try again after a send failure", async () => {
    const user = userEvent.setup();
    const sendMessage = vi
      .fn()
      .mockRejectedValueOnce(new Error("down"))
      .mockResolvedValueOnce({
        messages: [
          { id: "u1", role: "user", content: "Fix staff", toolName: null, toolStatus: null },
          {
            id: "a1",
            role: "assistant",
            content: "Staff is missing before the calendar route.",
            toolName: null,
            toolStatus: null,
          },
        ],
      });

    render(
      <ChatPage
        chatClient={chatClient({ sendMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix staff");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(
      await screen.findByText("Could not send that message. Check the model connection and try again."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^try again$/i }));

    expect(sendMessage).toHaveBeenCalledTimes(2);
    expect(sendMessage).toHaveBeenLastCalledWith("chat_1", "Fix staff", null);
    expect(
      await screen.findByText("Staff is missing before the calendar route."),
    ).toBeInTheDocument();
  });

  it("retries the last user message after a reply", async () => {
    const user = userEvent.setup();
    const sendMessage = vi
      .fn()
      .mockResolvedValueOnce({
        messages: [
          { id: "u1", role: "user", content: "Fix staff", toolName: null, toolStatus: null },
          {
            id: "a1",
            role: "assistant",
            content: "Staff is missing before the calendar route.",
            toolName: null,
            toolStatus: null,
          },
        ],
      })
      .mockResolvedValueOnce({
        messages: [
          { id: "u1", role: "user", content: "Fix staff", toolName: null, toolStatus: null },
          {
            id: "a1",
            role: "assistant",
            content: "Staff is missing before the calendar route.",
            toolName: null,
            toolStatus: null,
          },
          { id: "u2", role: "user", content: "Fix staff", toolName: null, toolStatus: null },
          {
            id: "a2",
            role: "assistant",
            content: "Create staff first.",
            toolName: null,
            toolStatus: null,
          },
        ],
      });

    render(
      <ChatPage
        chatClient={chatClient({ sendMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix staff");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(await screen.findByText("Staff is missing before the calendar route.")).toBeInTheDocument();

    await user.type(box, "draft keep");
    await user.click(screen.getByRole("button", { name: /^retry$/i }));

    expect(sendMessage).toHaveBeenLastCalledWith("chat_1", "Fix staff", null);
    expect(await screen.findByText("Create staff first.")).toBeInTheDocument();
    expect(box).toHaveValue("draft keep");
  });

  it("pastes a screenshot, lets you remove it, and sends it with the message", async () => {
    const user = userEvent.setup();
    const pngBytes = Uint8Array.from(atob(TINY_PNG_B64), (ch) => ch.charCodeAt(0));
    const png = new File([pngBytes], "shot.png", { type: "image/png" });
    const sendMessage = vi.fn(async () => ({
      messages: [
        {
          id: "u1",
          role: "user" as const,
          content: "What is this?\n![Pasted image](kronos-image:img_aaa)",
          toolName: null,
          toolStatus: null,
        },
        {
          id: "a1",
          role: "assistant" as const,
          content: "That is a screenshot.",
          toolName: null,
          toolStatus: null,
        },
      ],
    }));
    const getImage = vi.fn(async () => ({ mime: "image/png", data: TINY_PNG_B64 }));

    render(
      <ChatPage
        chatClient={chatClient({ sendMessage, getImage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    const imageInput = screen.getByLabelText(/add image/i);
    await user.upload(imageInput, png);
    expect(await screen.findByRole("img", { name: /pasted image/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /remove pasted image/i }));
    expect(screen.queryByRole("img", { name: /pasted image/i })).not.toBeInTheDocument();

    await user.upload(imageInput, png);
    await user.type(box, "What is this?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith("chat_1", "What is this?", null, [
        { mime: "image/png", data: TINY_PNG_B64 },
      ]);
    });
    expect(await screen.findByText("That is a screenshot.")).toBeInTheDocument();
    expect(getImage).toHaveBeenCalledWith("chat_1", "img_aaa");
  });

  it("rejects a pasted text file and can send an image with no caption", async () => {
    const user = userEvent.setup();
    const pngBytes = Uint8Array.from(atob(TINY_PNG_B64), (ch) => ch.charCodeAt(0));
    const png = new File([pngBytes], "shot.png", { type: "image/png" });
    const sendMessage = vi.fn(async () => ({
      messages: [
        {
          id: "u1",
          role: "user" as const,
          content: "![Pasted image](kronos-image:img_aaa)",
          toolName: null,
          toolStatus: null,
        },
        {
          id: "a1",
          role: "assistant" as const,
          content: "A screenshot.",
          toolName: null,
          toolStatus: null,
        },
      ],
    }));

    render(
      <ChatPage
        chatClient={chatClient({ sendMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    fireEvent.paste(box, {
      clipboardData: {
        files: [new File(["hello"], "note.txt", { type: "text/plain" })],
        items: [],
        types: ["Files"],
        getData: () => "",
      },
    });
    expect(await screen.findByText(/png, jpeg, webp, or gif/i)).toBeInTheDocument();

    const imageInput = screen.getByLabelText(/add image/i);
    await user.upload(imageInput, png);
    expect(await screen.findByRole("img", { name: /pasted image/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith("chat_1", "", null, [
        { mime: "image/png", data: TINY_PNG_B64 },
      ]);
    });
  });
});

const TINY_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
