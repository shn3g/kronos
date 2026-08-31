// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { HomePage, type HomePageClients } from "./HomePage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function clients(overrides: Partial<HomePageClients> = {}): HomePageClients {
  return {
    dashboard: async () => ({
      ready: true,
      repositories: [
        {
          id: "repo_alpha",
          displayName: "alpha",
          realpath: "C:/tmp/alpha",
          origin: "https://github.com/acme/alpha.git",
          status: "active",
        },
      ],
      schedules: [{ id: "goal_nightly", title: "Nightly scan", schedule: "0 4 * * *" }],
      budgets: [{ repositoryId: "repo_alpha", attempts: 1, breakerOpen: false }],
      runs: [{ id: "run_1", status: "succeeded", evidence: "tests/test_repro.py" }],
      diffs: [{ path: "pkg/math.py", summary: "+2 -1" }],
      tests: [{ name: "pytest", passed: true }],
      index: [{ repositoryId: "repo_alpha", ready: true, denseAvailable: false, chunkCount: 4 }],
    }),
    ...overrides,
  };
}

describe("HomePage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const dashboard = vi.fn(async () => clients().dashboard());
    render(<HomePage engineClient={engine("unavailable")} homeClient={clients({ dashboard })} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to open the dashboard/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /repository/i })).not.toBeInTheDocument();
    expect(dashboard).not.toHaveBeenCalled();
  });

  it("surfaces schedules, budgets, runs, diffs, tests, and index health", async () => {
    const user = userEvent.setup();
    render(<HomePage engineClient={engine("ready")} homeClient={clients()} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
    expect(await screen.findByText("Nightly scan")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /repository/i })).toBeInTheDocument();
    expect(screen.getByText(/breaker/i)).toBeInTheDocument();
    expect(screen.getByText(/tests\/test_repro\.py/)).toBeInTheDocument();
    expect(screen.getByText(/pkg\/math\.py/)).toBeInTheDocument();
    expect(screen.getByText(/pytest/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Index health" })).toBeInTheDocument();
    expect(screen.getByText(/4 chunks/)).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: /repository/i }), "repo_alpha");
    expect(screen.getByRole("combobox", { name: /repository/i })).toHaveValue("repo_alpha");
  });
});
