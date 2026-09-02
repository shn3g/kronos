// SPDX-License-Identifier: AGPL-3.0-or-later

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { IndexClient } from "../index/client";
import type {
  EmbeddingBackend,
  ModelsClient,
  RoleAssignments,
} from "../models/client";
import { embeddingInstallClientStubs } from "../models/client";
import { ChatPage } from "./ChatPage";
import type {
  ChatClient,
  ChatGoalEvent,
  ChatStreamHandlers,
  ChatToolEvent,
} from "./client";
import { STREAM_STATUS_SETTLE_MS } from "./streamStatus";

const TINY_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

const EMPTY_LIMITS = {
  maxTokens: 0,
  maxAttempts: 0,
  timeoutSeconds: 0,
  costCeiling: 0,
  contextWindow: 32_000,
};

function chatClient(overrides: Partial<ChatClient> = {}): ChatClient {
  return {
    listConversations: async () => [],
    createConversation: async (repositoryId) => ({
      id: "chat_1",
      title: "New chat",
      repositoryId,
      createdAt: "t",
    }),
    getConversation: async () => ({
      conversation: {
        id: "chat_1",
        title: "New chat",
        repositoryId: null,
        createdAt: "t",
      },
      messages: [],
    }),
    deleteConversation: async () => undefined,
    streamMessage: async (_id, _content, handlers) => {
      handlers.onDone({
        content: "Staff is missing before the calendar route.",
        citations: [],
        goalRefs: [],
      });
    },
    cancelStream: async () => undefined,
    getGoal: async () => ({ id: "goal_1", state: "draft", title: "" }),
    getImage: async () => ({ mime: "image/png", data: "" }),
    ...overrides,
  };
}

function idleIndex(search: IndexClient["search"]): IndexClient {
  const status = {
    repositoryId: "repo_alpha",
    commit: "abc",
    chunkCount: 4,
    denseAvailable: false,
    indexPath: "/tmp/index",
    ready: true,
    state: "idle" as const,
    filesDone: 0,
    filesTotal: 0,
    chunksEmbedded: 0,
    chunksSkipped: 0,
    lastActivityAt: null,
    watchEnabled: false,
  };
  return {
    status: async () => status,
    rebuild: async () => status,
    setWatch: async () => status,
    search,
  };
}

function emptyAssignments(): RoleAssignments {
  return {
    orchestrator: "prof_local",
    planner: "prof_plan",
    coder: "prof_code",
    reviewer: "prof_rev",
    embedding: "prof_emb",
  };
}

function embeddingBackend(): EmbeddingBackend {
  return { kind: "none", modelId: "", displayName: "Sparse only" };
}

function modelsClient(overrides: Partial<ModelsClient> = {}): ModelsClient {
  return {
    ...embeddingInstallClientStubs,
    snapshot: async () => ({
      detected: [],
      profiles: [
        {
          id: "prof_local",
          displayName: "Local llama",
          role: "orchestrator",
          billed: false,
          modelId: "llama3",
          limits: EMPTY_LIMITS,
        },
        {
          id: "prof_other",
          displayName: "Hosted gpt",
          role: "orchestrator",
          billed: true,
          modelId: "gpt-4o-mini",
          limits: { ...EMPTY_LIMITS, contextWindow: 8_000 },
        },
      ],
      assignments: emptyAssignments(),
      embeddingBackend: embeddingBackend(),
    }),
    assign: async (assignments) => assignments,
    createProvider: async () => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "Local",
        billed: false,
      },
      profiles: [],
    }),
    updateProfile: async (id) => ({
      id,
      displayName: id,
      role: "orchestrator",
      billed: false,
      modelId: "",
      limits: EMPTY_LIMITS,
    }),
    ...overrides,
  };
}

describe("ChatPage", () => {
  it("names the assigned model in the composer", async () => {
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        orchestratorName="Local llama"
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByText("Local llama")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /about \d+ of 32000 tokens/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Ask Kronos" })).toBeInTheDocument();
  });

  it("shows a one-line empty state when a workspace folder is open", async () => {
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId="repo_alpha"
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(
      await screen.findByText(/ask about this workspace, paste a screenshot, or type \/goal/i),
    ).toBeInTheDocument();
  });

  it("warns when the loaded thread is near the context window", async () => {
    render(
      <ChatPage
        chatClient={chatClient({
          listConversations: async () => [
            {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              createdAt: "t",
            },
          ],
          getConversation: async () => ({
            conversation: {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              createdAt: "t",
            },
            messages: [
              {
                id: "u1",
                role: "user",
                content: "x".repeat(110_000),
                citations: [],
                goalRefs: [],
                toolName: null,
                toolStatus: null,
                toolJson: null,
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

  it("shows the user message immediately and streams deltas", async () => {
    const user = userEvent.setup();
    let handlers!: ChatStreamHandlers;
    let finish!: () => void;
    const streamMessage = vi.fn((_id: string, _content: string, next: ChatStreamHandlers) => {
      handlers = next;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    });
    render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "What is broken in onboarding?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(await screen.findByText(/what is broken in onboarding/i)).toBeInTheDocument();
    expect(screen.getByText(/streaming reply/i)).toBeInTheDocument();

    await act(async () => {
      handlers.onDelta("Staff is ");
      handlers.onDelta("missing.");
    });
    expect(await screen.findByText(/staff is missing/i)).toBeInTheDocument();

    await act(async () => {
      handlers.onDone({ content: "Staff is missing.", citations: [], goalRefs: [] });
      finish();
    });
    expect(streamMessage).toHaveBeenCalledWith(
      "chat_1",
      "What is broken in onboarding?",
      expect.objectContaining({ requestId: expect.any(String) }),
    );
  });

  it("clears stream status on New chat so the empty state does not keep Turn finished", async () => {
    const user = userEvent.setup();
    let handlers!: ChatStreamHandlers;
    let finish!: () => void;
    const streamMessage = vi.fn((_id: string, _content: string, next: ChatStreamHandlers) => {
      handlers = next;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    });
    const { rerender } = render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
        repositoryId={null}
        historyOpen={false}
        newChatRequest={0}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "What is broken in onboarding?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await act(async () => {
      handlers.onDone({ content: "Staff is missing.", citations: [], goalRefs: [] });
      finish();
    });
    expect(await screen.findByText(/turn finished/i)).toBeInTheDocument();

    rerender(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
        repositoryId={null}
        historyOpen={false}
        newChatRequest={1}
        onOpenWorkspace={() => undefined}
      />,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Ask Kronos" })).toBeInTheDocument();
    expect(screen.queryByText(/turn finished/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/message failed/i)).not.toBeInTheDocument();
  });

  it("abandons an in-flight turn on New chat so a late onDone cannot stick the composer", async () => {
    const user = userEvent.setup();
    let handlers!: ChatStreamHandlers;
    let finish!: () => void;
    const cancelStream = vi.fn(async () => undefined);
    const streamMessage = vi.fn((_id: string, _content: string, next: ChatStreamHandlers) => {
      handlers = next;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    });
    const props = {
      chatClient: chatClient({ streamMessage, cancelStream }),
      repositoryId: null as string | null,
      historyOpen: false,
      onOpenWorkspace: () => undefined,
    };
    const { rerender } = render(<ChatPage {...props} newChatRequest={0} />);
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "What is broken in onboarding?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(await screen.findByRole("button", { name: /^stop$/i })).toBeInTheDocument();
    expect(screen.getByText(/streaming reply/i)).toBeInTheDocument();

    rerender(<ChatPage {...props} newChatRequest={1} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Ask Kronos" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^send$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^stop$/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/working/i)).not.toBeInTheDocument();
    expect(cancelStream).toHaveBeenCalledWith("chat_1", expect.any(String));

    await act(async () => {
      handlers.onDone({ content: "Staff is missing.", citations: [], goalRefs: [] });
      finish();
    });
    expect(screen.queryByText(/turn finished/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/staff is missing/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^send$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^stop$/i })).not.toBeInTheDocument();
  });

  it("does not reuse a conversation created after New chat during session setup", async () => {
    const user = userEvent.setup();
    let releaseFirst!: (summary: {
      id: string;
      title: string;
      repositoryId: string | null;
      createdAt: string;
    }) => void;
    const createConversation = vi.fn((repositoryId: string | null) => {
      const n = createConversation.mock.calls.length;
      const summary = {
        id: `chat_${n}`,
        title: "New chat",
        repositoryId,
        createdAt: "t",
      };
      if (n === 1) {
        return new Promise<typeof summary>((resolve) => {
          releaseFirst = resolve;
        });
      }
      return Promise.resolve(summary);
    });
    const streamMessage = vi.fn(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
      handlers.onDone({ content: "ok", citations: [], goalRefs: [] });
    });
    const props = {
      chatClient: chatClient({ createConversation, streamMessage }),
      repositoryId: null as string | null,
      historyOpen: false,
      onOpenWorkspace: () => undefined,
    };
    const { rerender } = render(<ChatPage {...props} newChatRequest={0} />);
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "First");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() => expect(createConversation).toHaveBeenCalledTimes(1));

    rerender(<ChatPage {...props} newChatRequest={1} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Ask Kronos" })).toBeInTheDocument();

    await act(async () => {
      releaseFirst({
        id: "chat_1",
        title: "New chat",
        repositoryId: null,
        createdAt: "t",
      });
    });

    const nextBox = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(nextBox, "Second");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() => expect(streamMessage).toHaveBeenCalled());
    expect(streamMessage).toHaveBeenCalledWith(
      "chat_2",
      "Second",
      expect.objectContaining({ requestId: expect.any(String) }),
    );
    expect(streamMessage.mock.calls.map((call) => call[0])).not.toContain("chat_1");
  });

  it("returns stream status to idle after a finished turn settles", async () => {
    const user = userEvent.setup();
    let handlers!: ChatStreamHandlers;
    let finish!: () => void;
    const streamMessage = vi.fn((_id: string, _content: string, next: ChatStreamHandlers) => {
      handlers = next;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    });
    render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "What is broken in onboarding?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await act(async () => {
      handlers.onDone({ content: "Staff is missing.", citations: [], goalRefs: [] });
      finish();
    });
    expect(await screen.findByText(/turn finished/i)).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.queryByText(/turn finished/i)).not.toBeInTheDocument();
      },
      { timeout: STREAM_STATUS_SETTLE_MS + 1000 },
    );
    expect(screen.getByText(/staff is missing/i)).toBeInTheDocument();
  });

  it("transitions a tool card from running to ok", async () => {
    const user = userEvent.setup();
    let handlers!: ChatStreamHandlers;
    let finish!: () => void;
    const streamMessage = vi.fn((_id: string, _content: string, next: ChatStreamHandlers) => {
      handlers = next;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    });
    render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Read the file");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await screen.findByText(/streaming reply/i);

    await act(async () => {
      const running: ChatToolEvent = {
        id: "t1",
        name: "read_file",
        status: "running",
        args: { path: "src/ok.ts" },
      };
      handlers.onTool?.(running);
    });
    expect(await screen.findByText("Read file · running.")).toBeInTheDocument();

    await act(async () => {
      handlers.onTool?.({
        id: "t1",
        name: "read_file",
        status: "ok",
        summary: "Read 12 lines",
        output: "const ok = true;",
      });
      handlers.onDone({ content: "That file is fine.", citations: [], goalRefs: [] });
      finish();
    });
    expect(await screen.findByText("Read file · done")).toBeInTheDocument();
    expect(screen.getByText("Read 12 lines")).toBeInTheDocument();
    expect(screen.getByText("const ok = true;")).toBeInTheDocument();
  });

  it("renders goal readiness and Open in Goals", async () => {
    const user = userEvent.setup();
    const onOpenGoals = vi.fn();
    const streamMessage = vi.fn(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
      const goal: ChatGoalEvent = {
        id: "goal_x",
        state: "draft",
        canExecute: false,
        readiness: [
          {
            id: "models_assigned",
            label: "Models",
            ok: false,
            detail: "Assign a planner, coder, and reviewer.",
          },
        ],
      };
      handlers.onGoal?.(goal);
      handlers.onDone({ content: "Draft goal created.", citations: [], goalRefs: ["goal_x"] });
    });
    render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
        onOpenGoals={onOpenGoals}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "/goal ship this");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(await screen.findByText(/assign a planner, coder, and reviewer/i)).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /open in goals/i }));
    expect(onOpenGoals).toHaveBeenCalled();
  });

  it("stop calls cancel on the stream and the conversation", async () => {
    const user = userEvent.setup();
    const cancelStream = vi.fn(async () => undefined);
    const streamMessage = vi.fn(
      (_id: string, _content: string, _handlers: ChatStreamHandlers) =>
        new Promise<void>(() => undefined),
    );
    render(
      <ChatPage
        chatClient={chatClient({ streamMessage, cancelStream })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Go");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await user.click(await screen.findByRole("button", { name: /^stop$/i }));
    expect(cancelStream).toHaveBeenCalledWith("chat_1", expect.any(String));
  });

  it("stops the current turn when Escape is pressed", async () => {
    const user = userEvent.setup();
    const cancelStream = vi.fn(async () => undefined);
    const streamMessage = vi.fn(
      (_id: string, _content: string, _handlers: ChatStreamHandlers) =>
        new Promise<void>(() => undefined),
    );
    render(
      <ChatPage
        chatClient={chatClient({ streamMessage, cancelStream })}
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
    expect(cancelStream).toHaveBeenCalledWith("chat_1", expect.any(String));
  });

  it("retries the last user message after a reply", async () => {
    const user = userEvent.setup();
    const streamMessage = vi
      .fn()
      .mockImplementationOnce(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
        handlers.onDone({
          content: "Staff is missing before the calendar route.",
          citations: [],
          goalRefs: [],
        });
      })
      .mockImplementationOnce(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
        handlers.onDone({ content: "Create staff first.", citations: [], goalRefs: [] });
      });

    render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
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

    expect(streamMessage).toHaveBeenLastCalledWith(
      "chat_1",
      "Fix staff",
      expect.objectContaining({ requestId: expect.any(String) }),
    );
    expect(await screen.findByText("Create staff first.")).toBeInTheDocument();
    expect(box).toHaveValue("draft keep");
  });

  it("caps pasted images at three per turn", async () => {
    const user = userEvent.setup();
    const pngBytes = Uint8Array.from(atob(TINY_PNG_B64), (ch) => ch.charCodeAt(0));
    const files = [1, 2, 3, 4].map(
      (index) => new File([pngBytes], `shot-${index}.png`, { type: "image/png" }),
    );
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );
    const imageInput = await screen.findByLabelText(/add image/i);
    await user.upload(imageInput, files);
    expect(await screen.findByText(/you can paste up to 3 images/i)).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /pasted image/i })).toHaveLength(3);
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
        indexClient={idleIndex(search)}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @app");
    await user.click(await screen.findByRole("option", { name: "src/App.tsx" }));
    expect(box).toHaveValue("Fix @src/App.tsx ");
    expect(search).toHaveBeenCalledWith("repo_alpha", "app");
  });

  it("assigns the orchestrator from the composer model switcher", async () => {
    const user = userEvent.setup();
    const assign = vi.fn(async (assignments: RoleAssignments) => assignments);
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        orchestratorName="Local llama"
        modelsClient={modelsClient({ assign })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Local llama" }));
    await user.click(await screen.findByRole("menuitem", { name: "Hosted gpt" }));
    expect(assign).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith({
      orchestrator: "prof_other",
      planner: "prof_plan",
      coder: "prof_code",
      reviewer: "prof_rev",
      embedding: "prof_emb",
    });
  });

  it("does not fill other roles from the selected orchestrator profile", async () => {
    const user = userEvent.setup();
    const assign = vi.fn(async (assignments: RoleAssignments) => assignments);
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        orchestratorName="Local llama"
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [],
            profiles: [
              {
                id: "prof_local",
                displayName: "Local llama",
                role: "orchestrator",
                billed: false,
                modelId: "llama3",
                limits: EMPTY_LIMITS,
              },
              {
                id: "prof_other",
                displayName: "Hosted gpt",
                role: "orchestrator",
                billed: true,
                modelId: "gpt-4o-mini",
                limits: { ...EMPTY_LIMITS, contextWindow: 8_000 },
              },
            ],
            assignments: { ...emptyAssignments(), planner: null },
            embeddingBackend: embeddingBackend(),
          }),
          assign,
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Local llama" }));
    await user.click(await screen.findByRole("menuitem", { name: "Hosted gpt" }));
    expect(assign).not.toHaveBeenCalled();
    expect(await screen.findByText(/could not switch the orchestrator/i)).toBeInTheDocument();
  });

  it("opens Connect a model as a dialog from the switcher", async () => {
    const user = userEvent.setup();
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        orchestratorName="Local llama"
        modelsClient={modelsClient()}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Local llama" }));
    await user.click(await screen.findByRole("menuitem", { name: /connect a model/i }));
    expect(await screen.findByRole("dialog", { name: /connect a model/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /connect a model/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /ask kronos/i })).toBeInTheDocument();
  });

  it("uses the orchestrator context window on the meter", async () => {
    render(
      <ChatPage
        chatClient={chatClient()}
        repositoryId={null}
        historyOpen={false}
        orchestratorName="Local llama"
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [],
            profiles: [
              {
                id: "prof_local",
                displayName: "Local llama",
                role: "orchestrator",
                billed: false,
                modelId: "llama3",
                limits: { ...EMPTY_LIMITS, contextWindow: 8_000 },
              },
            ],
            assignments: emptyAssignments(),
            embeddingBackend: embeddingBackend(),
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("progressbar", { name: /about \d+ of 8000 tokens/i })).toBeInTheDocument();
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

  it("applies a fenced file through onApplyFile", async () => {
    const user = userEvent.setup();
    const onApplyFile = vi.fn().mockResolvedValue(undefined);
    render(
      <ChatPage
        chatClient={chatClient({
          streamMessage: async (_id, _content, handlers) => {
            handlers.onDone({
              content: "```ts src/ok.ts\nconst ok = false;\n```\n",
              citations: [{ path: "src/math.py", startLine: 3, endLine: 5 }],
              goalRefs: [],
            });
          },
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
    expect(screen.getByText("src/math.py:3")).toBeInTheDocument();
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

  it("inserts the first mention on Enter instead of sending", async () => {
    const user = userEvent.setup();
    const streamMessage = vi.fn();
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
        chatClient={chatClient({ streamMessage })}
        repositoryId="repo_alpha"
        historyOpen={false}
        indexClient={idleIndex(search)}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @app");
    await screen.findByRole("option", { name: "src/App.tsx" });
    await user.keyboard("{Enter}");
    expect(box).toHaveValue("Fix @src/App.tsx ");
    expect(streamMessage).not.toHaveBeenCalled();
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
          ...idleIndex(search),
          status: async () => ({
            repositoryId: "repo_alpha",
            commit: null,
            chunkCount: 0,
            denseAvailable: false,
            indexPath: "/tmp/index",
            ready: false,
            state: "scanning",
            filesDone: 0,
            filesTotal: 0,
            chunksEmbedded: 0,
            chunksSkipped: 0,
            lastActivityAt: null,
            watchEnabled: false,
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

  it("lets you try again after a send failure", async () => {
    const user = userEvent.setup();
    const streamMessage = vi
      .fn()
      .mockImplementationOnce(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
        handlers.onError("Could not stream the orchestrator reply.");
      })
      .mockImplementationOnce(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
        handlers.onDone({
          content: "Staff is missing before the calendar route.",
          citations: [],
          goalRefs: [],
        });
      });

    render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
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

    expect(streamMessage).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("Staff is missing before the calendar route.")).toBeInTheDocument();
  });

  it("pastes a screenshot and sends it with the message", async () => {
    const user = userEvent.setup();
    const pngBytes = Uint8Array.from(atob(TINY_PNG_B64), (ch) => ch.charCodeAt(0));
    const png = new File([pngBytes], "shot.png", { type: "image/png" });
    const streamMessage = vi.fn(async (_id: string, _content: string, handlers: ChatStreamHandlers) => {
      handlers.onDone({ content: "That is a screenshot.", citations: [], goalRefs: [] });
    });

    render(
      <ChatPage
        chatClient={chatClient({ streamMessage })}
        repositoryId={null}
        historyOpen={false}
        onOpenWorkspace={() => undefined}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    const imageInput = screen.getByLabelText(/add image/i);
    await user.upload(imageInput, png);
    expect(await screen.findByRole("img", { name: /pasted image/i })).toBeInTheDocument();
    await user.type(box, "What is this?");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      expect(streamMessage).toHaveBeenCalledWith(
        "chat_1",
        "What is this?",
        expect.objectContaining({
          images: [{ mime: "image/png", data: TINY_PNG_B64 }],
        }),
      );
    });
    expect(await screen.findByText("That is a screenshot.")).toBeInTheDocument();
  });

  it("rejects a pasted text file", async () => {
    render(
      <ChatPage
        chatClient={chatClient()}
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
  });

  it("shows run_command output as preformatted text", async () => {
    render(
      <ChatPage
        chatClient={chatClient({
          listConversations: async () => [
            {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              createdAt: "t",
            },
          ],
          getConversation: async () => ({
            conversation: {
              id: "chat_1",
              title: "New chat",
              repositoryId: null,
              createdAt: "t",
            },
            messages: [
              {
                id: "u1",
                role: "user",
                content: "Run the tests.",
                citations: [],
                goalRefs: [],
                toolName: null,
                toolStatus: null,
                toolJson: null,
              },
              {
                id: "t1",
                role: "tool",
                content: "Exit 0\n\n3 passed",
                citations: [],
                goalRefs: [],
                toolName: "run_command",
                toolStatus: "ok",
                toolJson: '{"summary":"Exit 0","output":"Exit 0\\n\\n3 passed"}',
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

  it("lists current-repo and no-workspace history together", async () => {
    const listConversations = vi.fn(async (repositoryId: string | null) => {
      if (repositoryId === "repo_alpha") {
        return [
          {
            id: "chat_repo",
            title: "Repo chat",
            repositoryId: "repo_alpha",
            createdAt: "t",
          },
        ];
      }
      return [
        {
          id: "chat_loose",
          title: "Loose chat",
          repositoryId: null,
          createdAt: "t",
        },
      ];
    });
    render(
      <ChatPage
        chatClient={chatClient({ listConversations })}
        repositoryId="repo_alpha"
        historyOpen
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByText("Repo chat")).toBeInTheDocument();
    expect(screen.getByText("Loose chat")).toBeInTheDocument();
    expect(listConversations).toHaveBeenCalledWith("repo_alpha");
    expect(listConversations).toHaveBeenCalledWith(null);
  });
});
