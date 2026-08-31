// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { SkillsPage, type SkillsClient } from "./SkillsPage";
import type { SkillRecord } from "./client";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

const quarantined: SkillRecord = {
  id: "skill-useful-tdd-bbbbbbbbbbbb",
  name: "useful-tdd",
  revision: "b".repeat(40),
  locator: "fixture://useful",
  status: "quarantined",
  scope: "repo",
  description: "Write a failing test before implementation.",
  scan: {
    malicious: false,
    executedScripts: false,
    files: ["SKILL.md"],
    scripts: [],
    permissions: ["worktree_read"],
  },
};

function skillsClient(overrides: Partial<SkillsClient> = {}): SkillsClient {
  return {
    list: async () => [quarantined],
    importPack: async () => quarantined,
    evaluate: async () => ({ ...quarantined, status: "evaluated" }),
    approve: async () => ({ ...quarantined, status: "approved" }),
    activate: async () => ({ ...quarantined, status: "active" }),
    disable: async () => ({ ...quarantined, status: "disabled" }),
    ...overrides,
  };
}

describe("SkillsPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => [quarantined]);
    render(
      <SkillsPage engineClient={engine("unavailable")} skillsClient={skillsClient({ list })} />,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Skills" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to browse, quarantine, and activate skills/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /activate/i })).not.toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("shows quarantine status and can approve an evaluated skill", async () => {
    const user = userEvent.setup();
    const approve = vi.fn(async () => ({ ...quarantined, status: "approved" }));
    render(
      <SkillsPage
        engineClient={engine("ready")}
        skillsClient={skillsClient({ approve })}
      />,
    );

    expect(await screen.findByText("useful-tdd")).toBeInTheDocument();
    expect(screen.getByText(/^quarantined/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    expect(approve).toHaveBeenCalledWith("skill-useful-tdd-bbbbbbbbbbbb", true);
  });
});
