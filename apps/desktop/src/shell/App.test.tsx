import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
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

    expect(await screen.findByRole("status")).toHaveTextContent("Engine unavailable");
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
    await user.click(screen.getByRole("menuitem", { name: /^Edit$/ }));
    expect(screen.getByRole("menuitem", { name: /^cut$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^copy$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^paste$/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /^select all$/i })).toBeInTheDocument();
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
});
