import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../shell/App";
import type { EngineClient, EngineConnectionState } from "../engine/client";
import type { EmbeddingBackend, ModelsClient, RoleAssignments } from "../features/models/client";
import type { ChatClient } from "../features/chat/client";
import type { RepositoriesClient } from "../features/workspaces/client";
import type { HomeClient } from "../features/home/client";
import type { GoalsClient } from "../features/goals/client";
import type { SettingsPageClients } from "../features/settings/client";
import { ACTIVE_WORKSPACE_STORAGE_KEY } from "./resolveWorkspace";

const ENGINE_VERSION = "0.2.0";

function clientOf(state: EngineConnectionState): EngineClient {
  return {
    getState: async () => state,
  };
}

function embeddingBackend(): EmbeddingBackend {
  return { kind: "none", modelId: "", displayName: "Sparse only" };
}

function emptyAssignments(): RoleAssignments {
  return {
    orchestrator: null,
    planner: null,
    coder: null,
    reviewer: null,
    embedding: null,
  };
}

function assignedRoles(id: string): RoleAssignments {
  return {
    orchestrator: id,
    planner: id,
    coder: id,
    reviewer: id,
    embedding: id,
  };
}

function profile(id: string, role: string) {
  return {
    id,
    displayName: role === "orchestrator" ? "Local llama" : `Local (${role})`,
    role,
    billed: false,
    modelId: "llama3",
    limits: { maxTokens: 0, maxAttempts: 0, timeoutSeconds: 0, costCeiling: 0, contextWindow: 32000 },
  };
}

function emptyModels(): ModelsClient {
  return {
    snapshot: async () => ({
      detected: [],
      profiles: [],
      assignments: emptyAssignments(),
      embeddingBackend: embeddingBackend(),
    }),
    assign: async () => emptyAssignments(),
    createProvider: async () => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "Local",
        billed: false,
      },
      profiles: [profile("prof_1", "planner")],
    }),
    updateProfile: async (id) => profile(id, "planner"),
  };
}

function assignedModels(): ModelsClient {
  return {
    ...emptyModels(),
    snapshot: async () => ({
      detected: [],
      profiles: [profile("prof_local", "orchestrator")],
      assignments: assignedRoles("prof_local"),
      embeddingBackend: embeddingBackend(),
    }),
  };
}

function plannerOnlyModels(): ModelsClient {
  return {
    ...emptyModels(),
    snapshot: async () => ({
      detected: [],
      profiles: [profile("prof_plan", "planner")],
      assignments: {
        orchestrator: null,
        planner: "prof_plan",
        coder: "prof_plan",
        reviewer: "prof_plan",
        embedding: "prof_plan",
      },
      embeddingBackend: embeddingBackend(),
    }),
  };
}

function quietChat(): ChatClient {
  return {
    listConversations: async () => [],
    createConversation: async () => ({
      id: "chat_1",
      title: "New chat",
      repositoryId: "",
      createdAt: "2026-09-01T00:00:00+00:00",
    }),
    getConversation: async () => ({
      conversation: {
        id: "chat_1",
        title: "New chat",
        repositoryId: "",
        createdAt: "2026-09-01T00:00:00+00:00",
      },
      messages: [],
    }),
    deleteConversation: async () => undefined,
    streamMessage: async () => undefined,
    cancelStream: async () => undefined,
    getGoal: async () => ({ id: "goal_1", state: "draft", title: "" }),
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
    listChanges: async () => [],
    writeFile: unused,
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
    tick: async () => ({
      ok: true,
      status: "idle",
      reason: "",
      taskId: null,
      prUrl: null,
      terminal: false,
    }),
    get: unused,
    pollEvents: async () => ({ events: [], headSeq: 0 }),
  };
}

function quietSettings(): SettingsPageClients {
  return {
    load: async () => ({ otelExport: false, langfuseExport: false }),
    save: async (next) => next,
    doctor: async () => ({ ready: true, findings: [] }),
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

function readyFrame(extra: Record<string, unknown> = {}) {
  return {
    engineClient: clientOf({ status: "ready" as const, version: ENGINE_VERSION }),
    modelsClient: assignedModels(),
    chatClient: quietChat(),
    repositoriesClient: quietRepos(),
    homeClient: quietHome(),
    goalsClient: quietGoals(),
    settingsClient: quietSettings(),
    ...extra,
  };
}

describe("App shell", () => {
  beforeEach(() => {
    window.localStorage.removeItem(ACTIVE_WORKSPACE_STORAGE_KEY);
    window.localStorage.removeItem("kronos.activityBarCollapsed");
    window.localStorage.removeItem("kronos.inspectorCollapsed");
    window.location.hash = "";
  });

  it("shows engine unavailable by default without an injected client", async () => {
    render(<App />);

    expect(await screen.findByText(/engine unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
    expect(screen.queryByText(/engineering OS/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("menubar")).not.toBeInTheDocument();
  });

  it("does not open the main app until the local engine is connected", async () => {
    render(
      <App
        engineClient={clientOf({ status: "unavailable" })}
        modelsClient={assignedModels()}
        chatClient={quietChat()}
      />,
    );

    expect(
      await screen.findByRole("heading", { name: /local engine is not running/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "The local engine is not running" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^chat$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Home$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menubar")).not.toBeInTheDocument();
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

  it("blocks on connect a model before the chat chrome when no orchestrator is assigned", async () => {
    render(
      <App
        engineClient={clientOf({ status: "ready", version: ENGINE_VERSION })}
        modelsClient={emptyModels()}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    expect(await screen.findByRole("heading", { name: /connect a model/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^chat$/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/engineering OS/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("menubar")).not.toBeInTheDocument();
  });

  it("still requires Connect a model when only a planner is assigned", async () => {
    render(
      <App
        engineClient={clientOf({ status: "ready", version: ENGINE_VERSION })}
        modelsClient={plannerOnlyModels()}
        chatClient={quietChat()}
        repositoriesClient={quietRepos()}
        homeClient={quietHome()}
        goalsClient={quietGoals()}
        settingsClient={quietSettings()}
      />,
    );

    expect(await screen.findByRole("heading", { name: /connect a model/i })).toBeInTheDocument();
    expect(screen.queryByRole("menubar")).not.toBeInTheDocument();
  });

  it("does not say the engine is starting while the model snapshot loads", async () => {
    render(
      <App
        engineClient={clientOf({ status: "ready", version: ENGINE_VERSION })}
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
    expect(screen.queryByRole("heading", { name: /^chat$/i })).not.toBeInTheDocument();
  });

  it("opens a desktop frame with menus, chat, and inspector tabs once a model is assigned", async () => {
    const user = userEvent.setup();
    render(<App {...readyFrame()} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Ask Kronos" })).toBeInTheDocument();
    expect(screen.getByRole("menubar", { name: /application/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^File$/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^Edit$/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^View$/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^Help$/ })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /activity/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^goals$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /changes/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /goals/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /health/i })).toBeInTheDocument();
    expect(screen.queryByText(/engineering OS/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^files$/i }));
    expect(await screen.findByRole("heading", { level: 1, name: "Files" })).toBeInTheDocument();
    expect(screen.getByText(/the editor arrives later/i)).toBeInTheDocument();
    expect(
      screen.getByText(/open a git folder from workspaces to browse files here/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^chat$/i }));

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
  });

  it("puts Models under File and Cut Copy Paste under Edit", async () => {
    const user = userEvent.setup();
    render(<App {...readyFrame()} />);

    await screen.findByRole("heading", { level: 1, name: "Ask Kronos" });
    await user.click(screen.getByRole("menuitem", { name: /^File$/ }));
    expect(screen.getByRole("menuitem", { name: /^models$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^go to file$/i })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: /^models$/i }));
    expect(await screen.findByRole("heading", { name: /^models$/i })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/settings/models");

    await user.click(screen.getByRole("menuitem", { name: /^Edit$/ }));
    expect(screen.getByRole("menuitem", { name: /^cut$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^copy$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^paste$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^select all$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^find$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^find in files$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^replace$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^go to line$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^ask in chat$/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^models$/i })).not.toBeInTheDocument();
  });

  it("opens settings from the modifier comma shortcut and hides the inspector with Ctrl+Shift+J", async () => {
    const user = userEvent.setup();
    render(<App {...readyFrame()} />);

    await screen.findByRole("heading", { level: 1, name: "Ask Kronos" });
    await user.keyboard("{Control>}{Shift>}j{/Shift}{/Control}");
    expect(screen.queryByRole("complementary", { name: /session details/i })).not.toBeInTheDocument();
    await user.keyboard("{Control>},{/Control}");
    expect(await screen.findByRole("heading", { name: /^settings$/i })).toBeInTheDocument();
  });

  it("loads the workspace switcher and live Changes plus Goals from the engine", async () => {
    const user = userEvent.setup();
    render(<App {...readyFrame(liveSession())} />);

    expect(await screen.findByRole("combobox", { name: /workspace/i })).toHaveValue("repo_alpha");
    expect(await screen.findByText("src/App.tsx")).toBeInTheDocument();
    expect(screen.getByText(/guard staff/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /revert /i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^commit$/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /goals/i }));
    expect(await screen.findByText("Fix onboarding")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /health/i }));
    expect(await screen.findByText("Engine")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getAllByText("Ready").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText(/the local engine is running/i)).toBeInTheDocument();
    expect(screen.getByText(/orchestrator model is assigned/i)).toBeInTheDocument();
  });

  it("opens the Settings hub Models section from a hash deep link", async () => {
    window.location.hash = "#/settings/models";
    render(<App {...readyFrame()} />);

    expect(await screen.findByRole("heading", { name: /^models$/i })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /^settings$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^models$/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("selects the Goals activity from a hash deep link", async () => {
    window.location.hash = "#/goals";
    render(<App {...readyFrame()} />);

    expect(await screen.findByRole("heading", { name: /^goals$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^runs$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^goals$/i })).toHaveAttribute("aria-current", "page");
  });
});
