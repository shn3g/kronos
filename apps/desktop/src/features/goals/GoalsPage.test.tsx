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
    render(<GoalsPage engineClient={engine("ready")} goalsClient={clients()} />);

    expect(await screen.findByText("Fix add")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /fix add/i }));
    expect(await screen.findByText(/https:\/\/github.com\/acme\/app\/pull\/1/)).toBeInTheDocument();
  });
});
