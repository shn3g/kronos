// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { RunsPage, type RunsClient } from "./RunsPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

describe("RunsPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => []);
    render(<RunsPage engineClient={engine("unavailable")} runsClient={{ list, pollEvents: async () => ({ events: [], headSeq: 0 }) }} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("shows run evidence when the engine is ready", async () => {
    const list: RunsClient["list"] = async () => [
      {
        id: "run_1",
        goalId: "goal_1",
        taskId: "task_add",
        status: "succeeded",
        evidence: "tests/test_repro.py",
        prUrl: "https://github.com/acme/app/pull/1",
      },
    ];
    render(
      <RunsPage
        engineClient={engine("ready")}
        runsClient={{
          list,
          pollEvents: async () => ({ events: [], headSeq: 0 }),
        }}
      />,
    );

    expect(await screen.findByText(/task_add/)).toBeInTheDocument();
    expect(screen.getByText("tests/test_repro.py")).toBeInTheDocument();
    expect(screen.getByText("https://github.com/acme/app/pull/1")).toBeInTheDocument();
  });
});
