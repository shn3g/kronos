import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../shell/App";
import type { EngineClient, EngineConnectionState } from "../engine/client";
import type { ModelsClient } from "../features/models/client";
import type { ChatClient } from "../features/chat/client";
import type { RepositoriesClient } from "../features/workspaces/client";
import type { HomeClient } from "../features/home/client";
import type { GoalsClient } from "../features/goals/client";
import type { SettingsPageClients } from "../features/settings/client";
import { ACTIVE_WORKSPACE_STORAGE_KEY } from "./resolveWorkspace";

function clientOf(state: EngineConnectionState): EngineClient {
  return {
    getState: async () => state,
  };
}

function emptyModels(): ModelsClient {
  return {
    snapshot: async () => ({
      detected: [],
      profiles: [],
      assignments: {
        planner: null,
        coder: null,
        reviewer: null,
        embedding: null,
      },
    }),
    assign: async () => ({
      planner: null,
      coder: null,
      reviewer: null,
      embedding: null,
    }),
    createProvider: async () => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "Local",
        billed: false,
      },
      profiles: [{ id: "prof_1", displayName: "Local (planner)", role: "planner", billed: false }],
    }),
  };
}

function assignedModels(): ModelsClient {
  return {
    ...emptyModels(),
    snapshot: async () => ({
      detected: [],
      profiles: [{ id: "prof_local", displayName: "Local llama", role: "planner", billed: false }],
      assignments: {
        planner: "prof_local",
        coder: "prof_local",
        reviewer: "prof_local",
        embedding: "prof_local",
      },
    }),
  };
}

function quietChat(): ChatClient {
  return {
    listSessions: async () => [],
    createSession: async () => ({
      id: "chat_1",
      title: "New chat",
      repositoryId: null,
      updatedAt: "2026-09-01T00:00:00+00:00",
    }),
    getSession: async () => ({
      session: {
        id: "chat_1",
        title: "New chat",
        repositoryId: null,
        updatedAt: "2026-09-01T00:00:00+00:00",
      },
      messages: [],
    }),
    sendMessage: async () => ({ messages: [] }),
    cancelTurn: async () => undefined,
    getImage: async () => ({ mime: "image/png", data: "" }),
  };
}

async function unused(): Promise<never> {
  throw new Error("unused");
}

function quietRepos(): RepositoriesClient {
  return {
    list: async () => [],
    inspect: unused,
    enrol: unused,
    pause: unused,
    disable: unused,
    resume: unused,
    revertWrite: unused,
    listChanges: async () => [],
    commitFiles: unused,
    listWorkspaceFiles: async () => [],
    readWorkspaceFile: unused,
    writeWorkspaceFile: unused,
    runWorkspaceCommand: unused,
    startWorkspaceShell: unused,
    writeWorkspaceShell: unused,
    cancelWorkspaceCommand: unused,
    watchWorkspaceCommand: unused,
  };
}

function quietHome(): HomeClient {
  return {
    dashboard: async () => ({
      ready: true,
      repositories: [],
      schedules: [],
      budgets: [],
      runs: [],
      diffs: [],
      tests: [],
      index: [],
    }),
  };
}

function quietGoals(): GoalsClient {
  return {
    list: async () => [],
    create: unused,
    plan: unused,
    tick: unused,
    get: unused,
    pollEvents: unused,
  };
}

function quietSettings(): SettingsPageClients {
  return {
    load: async () => ({ otelExport: false, langfuseExport: false }),
    save: async (next) => next,
    doctor: async () => ({ ready: true, findings: [], checks: [] }),
    backup: async () => ({ path: "", includesSecretStore: false }),
  };
}

function liveSession() {
  return {
    repositoriesClient: {
      ...quietRepos(),
      list: async () => [
        {
          id: "repo_alpha",
          displayName: "dashboard.klikday.com",
          realpath: "C:/tmp/alpha",
          origin: null,
          status: "active" as const,
        },
      ],
      listChanges: async () => [
        {
          path: "src/App.tsx",
          summary: "guard staff before calendar",
          patch: "",
          status: "M",
          fromChat: true,
        },
      ],
    },
    homeClient: {
      dashboard: async () => ({
        ready: true,
        repositories: [
          {
            id: "repo_alpha",
            displayName: "dashboard.klikday.com",
            realpath: "C:/tmp/alpha",
            origin: null,
            status: "active",
          },
        ],
        schedules: [],
        budgets: [],
        runs: [],
        diffs: [
          {
            path: "src/App.tsx",
            summary: "guard staff before calendar",
            repositoryId: "repo_alpha",
          },
        ],
        tests: [],
        index: [{ repositoryId: "repo_alpha", ready: true, denseAvailable: false, chunkCount: 4 }],
      }),
    },
    goalsClient: {
      ...quietGoals(),
      list: async () => [
        {
          id: "goal_1",
          repositoryId: "repo_alpha",
          title: "Fix onboarding",
          state: "queued",
          source: "desktop",
          riskCeiling: "low",
          successCriteria: "staff exists before calendar",
          nonGoals: "rewrite billing",
          stopReason: null,
          schedule: null,
          maxAttempts: 3,
        },
      ],
    },
    settingsClient: quietSettings(),
  };
}

describe("App shell", () => {
  beforeEach(() => {
    window.localStorage.removeItem(ACTIVE_WORKSPACE_STORAGE_KEY);
    window.localStorage.removeItem("kronos.activityBarCollapsed");
    window.localStorage.removeItem("kronos.inspectorCollapsed");
  });

  it("shows engine unavailable by default without an injected client", async () => {
    render(<App />);

    expect(await screen.findByText(/engine unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
    expect(screen.queryByText(/engineering OS/i)).not.toBeInTheDocument();
  });

  it("does not open the main app until the local engine is connected", async () => {
    render(
      <App
        engineClient={clientOf({ status: "unavailable" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
      />,
    );

    expect(await screen.findByRole("heading", { name: /local engine is not running/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /ask kronos/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Home$/ })).not.toBeInTheDocument();
  });

  it("does not say the engine is not running before the first probe returns", async () => {
    let release!: (state: EngineConnectionState) => void;
    render(
      <App
        engineClient={{
          getState: () =>
            new Promise<EngineConnectionState>((resolve) => {
              release = resolve;
            }),
        }}
        modelsClient={emptyModels()}
        chatClient={quietChat()}
      />,
    );

    expect(screen.getByRole("heading", { name: /starting kronos/i })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Engine starting");
    expect(
      screen.queryByRole("heading", { name: /local engine is not running/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
    release({ status: "unavailable" });
    expect(
      await screen.findByRole("heading", { name: /local engine is not running/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Engine unavailable");
    expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
  });

  it("treats a rejecting engine client as unavailable", async () => {
    render(
      <App
        engineClient={{
          getState: async () => {
            throw new Error("engine probe failed");
          },
        }}
        modelsClient={emptyModels()}
        chatClient={quietChat()}
      />,
    );

    expect(
      await screen.findByRole("heading", { name: /local engine is not running/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Engine unavailable");
    expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
  });

  it("blocks on connect a model before the chat chrome when no provider is assigned", async () => {
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={emptyModels()}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    expect(await screen.findByRole("heading", { name: /connect a model/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /ask kronos/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/engineering OS/i)).not.toBeInTheDocument();
  });

  it("does not say the engine is starting while the model snapshot loads", async () => {
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={{
          ...emptyModels(),
          snapshot: () => new Promise(() => undefined),
        }}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    expect(
      await screen.findByRole("heading", { name: /checking the model connection/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/starting kronos/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /ask kronos/i })).not.toBeInTheDocument();
  });

  it("opens a desktop frame with menus, chat, and inspector tabs once a model is assigned", async () => {
    const user = userEvent.setup();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    expect(await screen.findByRole("textbox", { name: /ask kronos/i })).toBeInTheDocument();
    expect(screen.getByText("Local llama")).toBeInTheDocument();
    expect(screen.getByRole("menubar", { name: /application/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^File$/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^Edit$/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^View$/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^Help$/ })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /activity/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /changes/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /goals/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /health/i })).toBeInTheDocument();
    expect(screen.queryByText(/engineering OS/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^files$/i }));
    expect(await screen.findByRole("heading", { level: 1, name: "Files" })).toBeInTheDocument();
    expect(
      screen.getByText(/open a git folder from workspaces to browse files here/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^chat$/i }));

    await user.click(screen.getByRole("menuitem", { name: /^View$/ }));
    await user.click(screen.getByRole("menuitem", { name: /chat history/i }));
    expect(screen.getByRole("complementary", { name: /chat history/i })).toBeInTheDocument();

    await user.click(screen.getByRole("menuitem", { name: /^View$/ }));
    await user.click(screen.getByRole("menuitem", { name: /hide activity bar/i }));
    expect(screen.queryByRole("navigation", { name: /activity/i })).not.toBeInTheDocument();
    expect(document.querySelector(".app-body")).toHaveAttribute("data-rail-collapsed", "true");

    await user.click(screen.getByRole("menuitem", { name: /^View$/ }));
    await user.click(screen.getByRole("menuitem", { name: /hide inspector/i }));
    expect(screen.queryByRole("complementary", { name: /session details/i })).not.toBeInTheDocument();
    expect(document.querySelector(".app-columns")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );

    expect(screen.queryByRole("region", { name: /terminal/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: /^View$/ }));
    await user.click(screen.getByRole("menuitem", { name: /^terminal$/i }));
    expect(await screen.findByRole("region", { name: /terminal/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Terminal" })).toBeInTheDocument();
  });

  it("puts Models under File and Cut Copy Paste under Edit", async () => {
    const user = userEvent.setup();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.click(screen.getByRole("menuitem", { name: /^File$/ }));
    expect(screen.getByRole("menuitem", { name: /^models$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^go to file$/i })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: /^Edit$/ }));
    expect(screen.getByRole("menuitem", { name: /^cut$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^copy$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^paste$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^select all$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^find$/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^models$/i })).not.toBeInTheDocument();
  });

  it("opens settings from the modifier comma shortcut and hides the inspector with Ctrl+Shift+J", async () => {
    const user = userEvent.setup();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.keyboard("{Control>}{Shift>}j{/Shift}{/Control}");
    expect(screen.queryByRole("complementary", { name: /session details/i })).not.toBeInTheDocument();
    await user.keyboard("{Control>}`{/Control}");
    expect(await screen.findByRole("region", { name: /terminal/i })).toBeInTheDocument();
    await user.keyboard("{Control>},{/Control}");
    expect(await screen.findByRole("heading", { name: /^settings$/i })).toBeInTheDocument();
  });

  it("loads the workspace switcher and live Changes plus Goals from the engine", async () => {
    const user = userEvent.setup();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        {...liveSession()}
      />,
    );

    expect(await screen.findByRole("combobox", { name: /workspace/i })).toHaveValue("repo_alpha");
    expect(await screen.findByText("src/App.tsx")).toBeInTheDocument();
    expect(screen.getByText(/guard staff/i)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /goals/i }));
    expect(await screen.findByText("Fix onboarding")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /health/i }));
    expect(await screen.findByText("Engine")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getAllByText("Ready").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText(/the local engine is running/i)).toBeInTheDocument();
  });

  it("opens Models from the composer model name", async () => {
    const user = userEvent.setup();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.click(screen.getByRole("button", { name: "Local llama" }));
    expect(await screen.findByRole("heading", { name: /^models$/i })).toBeInTheDocument();
  });

  it("reverts a chat write from the Changes list", async () => {
    const user = userEvent.setup();
    let changes = [
      {
        path: "src/App.tsx",
        summary: "guard staff before calendar",
        patch: "",
        status: "M",
        fromChat: true,
      },
    ];
    const revertWrite = vi.fn(async () => {
      changes = [];
    });
    const session = liveSession();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          revertWrite,
          listChanges: async () => changes,
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    expect(await screen.findByText("src/App.tsx")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /revert src\/app\.tsx/i }));
    expect(revertWrite).toHaveBeenCalledWith("repo_alpha", "src/App.tsx");
    expect(
      await screen.findByText(/no file changes in this workspace yet/i),
    ).toBeInTheDocument();
  });

  it("explains when a chat write cannot be reverted", async () => {
    const user = userEvent.setup();
    const session = liveSession();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          revertWrite: async () => {
            throw new Error("engine request failed: 409");
          },
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    expect(await screen.findByText("src/App.tsx")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /revert src\/app\.tsx/i }));
    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("Could not revert that file. Check the workspace and try again.");
    expect(screen.getByText("src/App.tsx")).toBeInTheDocument();
  });

  it("commits listed working-tree files from Changes", async () => {
    const user = userEvent.setup();
    let changes = [
      {
        path: "src/App.tsx",
        summary: "guard staff before calendar",
        patch: "",
        status: "M",
        fromChat: true,
      },
    ];
    const commitFiles = vi.fn(async () => {
      changes = [];
    });
    const session = liveSession();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          listChanges: async () => changes,
          commitFiles,
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    expect(await screen.findByText("src/App.tsx")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /commit message/i }), "Fix App");
    await user.click(screen.getByRole("button", { name: /^commit$/i }));
    expect(commitFiles).toHaveBeenCalledWith("repo_alpha", "Fix App", ["src/App.tsx"]);
    expect(
      await screen.findByText(/no file changes in this workspace yet/i),
    ).toBeInTheDocument();
  });

  it("explains when a local commit cannot be recorded", async () => {
    const user = userEvent.setup();
    const session = liveSession();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          commitFiles: async () => {
            throw new Error("engine request failed: 409");
          },
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    expect(await screen.findByText("src/App.tsx")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /commit message/i }), "Fix App");
    await user.click(screen.getByRole("button", { name: /^commit$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not commit those files. Check the message and try again.",
    );
    expect(screen.getByText("src/App.tsx")).toBeInTheDocument();
  });

  it("mentions a workspace file in chat from the Files preview", async () => {
    const user = userEvent.setup();
    const session = liveSession();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          listWorkspaceFiles: async () => [{ path: "src/app.py" }],
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "print(1)\n",
            binary: false,
          }),
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.click(screen.getByRole("button", { name: /^files$/i }));
    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    await user.click(await screen.findByRole("button", { name: /ask in chat/i }));
    expect(await screen.findByRole("textbox", { name: /ask kronos/i })).toHaveValue("@src/app.py ");
  });

  it("opens a mentioned file in Files from the chat thread", async () => {
    const user = userEvent.setup();
    const session = liveSession();
    const readWorkspaceFile = vi.fn(async (_id: string, path: string) => ({
      path,
      content: "print(1)\n",
      binary: false,
    }));
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={{
          ...quietChat(),
          sendMessage: async (_id, content) => ({
            messages: [
              { id: "u1", role: "user", content, toolName: null, toolStatus: null },
              {
                id: "a1",
                role: "assistant",
                content: "I will inspect that file.",
                toolName: null,
                toolStatus: null,
              },
            ],
          }),
        }}
        repositoriesClient={{
          ...session.repositoriesClient,
          listWorkspaceFiles: async () => [{ path: "src/app.py" }],
          readWorkspaceFile,
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    const box = await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.type(box, "Fix @src/app.py");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await user.click(await screen.findByRole("button", { name: /open src\/app\.py/i }));

    expect(await screen.findByRole("heading", { level: 1, name: "Files" })).toBeInTheDocument();
    expect(await screen.findByRole("textbox", { name: "src/app.py" })).toHaveValue("print(1)\n");
    expect(readWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/app.py");
  });

  it("opens a changed file in Files from the Changes list", async () => {
    const user = userEvent.setup();
    const session = liveSession();
    const readWorkspaceFile = vi.fn(async (_id: string, path: string) => ({
      path,
      content: "export function App() {}\n",
      binary: false,
    }));
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          listWorkspaceFiles: async () => [{ path: "src/App.tsx" }],
          readWorkspaceFile,
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.click(await screen.findByRole("button", { name: /open src\/app\.tsx/i }));

    expect(await screen.findByRole("heading", { level: 1, name: "Files" })).toBeInTheDocument();
    expect(await screen.findByRole("textbox", { name: "src/App.tsx" })).toHaveValue(
      "export function App() {}\n",
    );
    expect(readWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/App.tsx");
  });

  it("opens a workspace file from Go to file with Ctrl+P", async () => {
    const user = userEvent.setup();
    const session = liveSession();
    const readWorkspaceFile = vi.fn(async (_id: string, path: string) => ({
      path,
      content: "print(1)\n",
      binary: false,
    }));
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          listWorkspaceFiles: async () => [{ path: "src/app.py" }, { path: "README.md" }],
          readWorkspaceFile,
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.keyboard("{Control>}p{/Control}");
    await screen.findByRole("option", { name: "src/app.py" });
    await user.type(screen.getByRole("combobox", { name: /go to file/i }), "app");
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("heading", { level: 1, name: "Files" })).toBeInTheDocument();
    expect(await screen.findByRole("textbox", { name: "src/app.py" })).toHaveValue("print(1)\n");
    expect(readWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/app.py");
    expect(screen.queryByRole("dialog", { name: /go to file/i })).not.toBeInTheDocument();
  });

  it("keeps unsaved Files edits when switching back from Chat", async () => {
    const user = userEvent.setup();
    const session = liveSession();
    render(
      <App
        engineClient={clientOf({ status: "ready", version: "0.1.0" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
        repositoriesClient={{
          ...session.repositoriesClient,
          listWorkspaceFiles: async () => [{ path: "src/app.py" }],
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "print(1)\n",
            binary: false,
          }),
        }}
        homeClient={session.homeClient}
        goalsClient={session.goalsClient}
        settingsClient={session.settingsClient}
      />,
    );

    await screen.findByRole("textbox", { name: /ask kronos/i });
    await user.click(screen.getByRole("button", { name: /^files$/i }));
    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const open = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.type(open, "x");
    await user.click(screen.getByRole("button", { name: /^chat$/i }));
    expect(await screen.findByRole("textbox", { name: /ask kronos/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^files$/i }));
    expect(await screen.findByRole("textbox", { name: "src/app.py" })).toHaveValue("print(1)\nx");
  });
});
