// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import type { RunsClient } from "../runs/client";
import type { RepositoriesClient } from "../workspaces/client";
import { GoalsWorkbench, type GoalsWorkbenchClients } from "./GoalsWorkbench";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

const goalRecord = {
  id: "goal_1",
  repositoryId: "repo_alpha",
  title: "Fix add",
  state: "planned",
  source: "desktop",
  riskCeiling: "low",
  successCriteria: "add(1, 1) == 2",
  nonGoals: "rewrite packaging",
  stopReason: null,
  schedule: null,
  maxAttempts: 3,
};

function clients(overrides: Partial<GoalsWorkbenchClients> = {}): GoalsWorkbenchClients {
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
    list: async () => [goalRecord],
    create: async () => {
      throw new Error("create should not run");
    },
    get: async () => ({
      goal: goalRecord,
      tasks: [
        {
          id: "task_add",
          goalId: "goal_1",
          title: "fix add",
          state: "ready",
          kind: "implementation",
          stopReason: null,
          prUrl: null,
          prBase: null,
        },
      ],
    }),
    pollEvents: async () => ({ events: [], headSeq: 0 }),
    plan: vi.fn(async () => ({
      goal: goalRecord,
      tasks: [],
    })),
    tick: vi.fn(async () => ({
      ok: true,
      status: "idle",
      reason: "no ready task",
      taskId: null,
      prUrl: null,
      terminal: false,
    })),
    goalReadiness: async () => ({
      canExecute: false,
      checks: [
        {
          id: "workspace_active",
          label: "Workspace",
          ok: true,
          detail: "Workspace is active.",
        },
        {
          id: "models_assigned",
          label: "Models assigned",
          ok: false,
          detail: "Assign planner, coder, and reviewer on the Models page.",
        },
      ],
    }),
    ...overrides,
  };
}

function repos(overrides: Partial<RepositoriesClient> = {}): RepositoriesClient {
  return {
    list: async () => [],
    get: async () => ({
      repository: {
        id: "repo_alpha",
        displayName: "alpha",
        realpath: "C:/tmp/alpha",
        origin: null,
        status: "active",
      },
      policy: { autonomy: { mode: "write_draft_prs", freeze: false } },
      runtime: {},
    }),
    inspect: async () => {
      throw new Error("unused");
    },
    enrol: async () => {
      throw new Error("unused");
    },
    pause: async () => {
      throw new Error("unused");
    },
    disable: async () => {
      throw new Error("unused");
    },
    resume: async () => {
      throw new Error("unused");
    },
    listChanges: async () => [],
    listWorkspaceFiles: async () => [],
    readWorkspaceFile: async () => {
      throw new Error("unused");
    },
    writeFile: async () => undefined,
    writeWorkspaceFile: async () => undefined,
    revertWrite: async () => undefined,
    commitFiles: async () => undefined,
    runWorkspaceCommand: async () => ({
      command: "",
      exitCode: 0,
      timedOut: false,
      cancelled: false,
      output: "",
    }),
    startWorkspaceShell: async () => ({
      command: "shell",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: "",
    }),
    writeWorkspaceShell: async () => ({ ok: true }),
    resizeWorkspaceShell: async () => ({ ok: true }),
    watchWorkspaceCommand: async () => ({
      command: "",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: "",
    }),
    cancelWorkspaceCommand: async () => ({ ok: true }),
    ...overrides,
  };
}

function runs(overrides: Partial<RunsClient> = {}): RunsClient {
  return {
    list: async () => [
      {
        id: "run_1",
        goalId: "goal_1",
        taskId: "task_add",
        status: "succeeded",
        evidence: "tests/test_repro.py",
        prUrl: null,
      },
      {
        id: "run_2",
        goalId: "goal_other",
        taskId: "task_other",
        status: "succeeded",
        evidence: "tests/other.py",
        prUrl: null,
      },
    ],
    pollEvents: async () => ({ events: [], headSeq: 0 }),
    ...overrides,
  };
}

describe("GoalsWorkbench", () => {
  it("renders readiness checks; failed check has a fix link to the mapped Settings href", async () => {
    const user = userEvent.setup();
    render(
      <GoalsWorkbench
        engineClient={engine("ready")}
        goalsClient={clients()}
        repositoriesClient={repos()}
        runsClient={runs()}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /fix add/i }));
    expect(await screen.findByText("Models assigned")).toBeInTheDocument();
    expect(screen.getByText("needs attention")).toBeInTheDocument();
    const fixLink = screen.getByRole("link", { name: /fix models assigned/i });
    expect(fixLink).toHaveAttribute("href", "#/settings/models");
  });

  it("calls plan when the Plan button is clicked", async () => {
    const user = userEvent.setup();
    const plan = vi.fn(async () => ({
      goal: goalRecord,
      tasks: [],
    }));
    render(
      <GoalsWorkbench
        engineClient={engine("ready")}
        goalsClient={clients({ plan })}
        repositoriesClient={repos()}
        runsClient={runs()}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /fix add/i }));
    await user.click(screen.getByRole("button", { name: /^plan$/i }));
    expect(plan).toHaveBeenCalledWith("goal_1");
  });

  it("shows run evidence for the selected goal", async () => {
    const user = userEvent.setup();
    render(
      <GoalsWorkbench
        engineClient={engine("ready")}
        goalsClient={clients()}
        repositoriesClient={repos()}
        runsClient={runs()}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /fix add/i }));
    expect(await screen.findByText("tests/test_repro.py")).toBeInTheDocument();
    expect(screen.queryByText("tests/other.py")).not.toBeInTheDocument();
  });
});
