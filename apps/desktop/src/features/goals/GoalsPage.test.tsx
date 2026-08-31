// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { GoalsPage, type GoalsPageClients } from "./GoalsPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function clients(overrides: Partial<GoalsPageClients> = {}): GoalsPageClients {
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
    list: async () => [
      {
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
      },
    ],
    create: async () => {
      throw new Error("create should not run");
    },
    get: async () => ({
      goal: {
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
      },
      tasks: [
        {
          id: "task_add",
          goalId: "goal_1",
          title: "fix add",
          state: "ready",
          kind: "implementation",
          stopReason: null,
          prUrl: "https://github.com/acme/app/pull/1",
          prBase: "integration",
        },
      ],
    }),
    pollEvents: async () => ({ events: [], headSeq: 0 }),
    plan: async () => {
      throw new Error("plan should not run");
    },
    tick: async () => ({
      ok: true,
      status: "idle",
      reason: "no ready task",
      taskId: null,
      prUrl: null,
      terminal: false,
    }),
    ...overrides,
  };
}

describe("GoalsPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => []);
    render(<GoalsPage engineClient={engine("unavailable")} goalsClient={clients({ list })} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Goals" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to create and track bounded goals/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create goal/i })).not.toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("lists goals and tasks when the engine is ready", async () => {
    const user = userEvent.setup();
    const pollEvents = vi.fn(async () => ({ events: [], headSeq: 0 }));
    const tick = vi.fn(async () => ({
      ok: true,
      status: "idle",
      reason: "no ready task",
      taskId: null,
      prUrl: null,
      terminal: false,
    }));
    render(
      <GoalsPage engineClient={engine("ready")} goalsClient={clients({ pollEvents, tick })} />,
    );

    expect(await screen.findByText("Fix add")).toBeInTheDocument();
    expect(await screen.findByLabelText(/attempt budget/i)).toBeInTheDocument();
    expect(pollEvents).toHaveBeenCalled();
    expect(tick).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /fix add/i }));
    expect(await screen.findByText(/https:\/\/github.com\/acme\/app\/pull\/1/)).toBeInTheDocument();
  });

  it("plans after create and polls tick while ready", async () => {
    const user = userEvent.setup();
    const plan = vi.fn(async (id: string) => ({
      goal: {
        id,
        repositoryId: "repo_alpha",
        title: "New goal",
        state: "planned",
        source: "desktop",
        riskCeiling: "low",
        successCriteria: "works",
        nonGoals: "none",
        stopReason: null,
        schedule: null,
        maxAttempts: 3,
      },
      tasks: [],
    }));
    const create = vi.fn(async () => ({
      id: "goal_new",
      repositoryId: "repo_alpha",
      title: "New goal",
      state: "draft",
      source: "desktop",
      riskCeiling: "low",
      successCriteria: "works",
      nonGoals: "none",
      stopReason: null,
      schedule: null,
      maxAttempts: 3,
    }));
    const tick = vi.fn(async () => ({
      ok: true,
      status: "idle",
      reason: "no ready task",
      taskId: null,
      prUrl: null,
      terminal: false,
    }));
    render(
      <GoalsPage
        engineClient={engine("ready")}
        goalsClient={clients({ create, plan, tick, list: async () => [] })}
      />,
    );

    await screen.findByRole("button", { name: /create goal/i });
    await user.click(screen.getByRole("button", { name: /create goal/i }));
    expect(create).toHaveBeenCalled();
    expect(plan).toHaveBeenCalledWith("goal_new");
    await screen.findByText("New goal");
    expect(tick).toHaveBeenCalled();
  });
});
