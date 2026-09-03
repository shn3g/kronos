// SPDX-License-Identifier: AGPL-3.0-or-later

import { screen } from "@testing-library/react";
import { renderWithEngineConnection } from "../../engine/testUtils";
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
  capabilities: ["tdd", "write_tests"],
  scan: {
    malicious: false,
    executedScripts: false,
    files: ["SKILL.md", "regression.yaml"],
    scripts: ["scripts/setup.py"],
    permissions: ["worktree_read"],
    findings: [{ path: "SKILL.md", code: "network", detail: "mentions urllib" }],
  },
};

const malicious: SkillRecord = {
  ...quarantined,
  id: "skill-malicious-cccccccccccccccc",
  name: "malicious-exfil",
  status: "quarantined",
  capabilities: ["review"],
  scan: {
    ...quarantined.scan,
    malicious: true,
    files: ["SKILL.md", "scripts/exfil.py"],
    scripts: ["scripts/exfil.py"],
    findings: [{ path: "scripts/exfil.py", code: "secrets", detail: "GH_TOKEN" }],
  },
};

function skillsClient(overrides: Partial<SkillsClient> = {}): SkillsClient {
  return {
    list: async () => [quarantined],
    importPack: async () => quarantined,
    evaluate: async () => ({ ...quarantined, status: "evaluated" }),
    approve: async () => ({ ...quarantined, status: "approved" }),
    activate: async () => ({ ...quarantined, status: "active" }),
    promote: async () => quarantined,
    disable: async () => ({ ...quarantined, status: "disabled" }),
    ...overrides,
  };
}

describe("SkillsPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => [quarantined]);
    renderWithEngineConnection(<SkillsPage
skillsClient={skillsClient({ list })} />, engine("unavailable"));

    expect(await screen.findByRole("heading", { level: 1, name: "Skills" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /activate/i })).not.toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("shows quarantine status and can approve an evaluated skill", async () => {
    const user = userEvent.setup();
    const approve = vi.fn(async () => ({ ...quarantined, status: "approved" }));
    renderWithEngineConnection(<SkillsPage
skillsClient={skillsClient({ approve })}
      />, engine("ready"));

    expect(await screen.findByText("useful-tdd")).toBeInTheDocument();
    expect(screen.getByText(/^quarantined/)).toBeInTheDocument();
    expect(screen.getByText(/Capabilities: tdd, write_tests/i)).toBeInTheDocument();
    expect(screen.getByText(/Files: SKILL.md, regression.yaml/i)).toBeInTheDocument();
    expect(screen.getByText(/Scripts: scripts\/setup.py/i)).toBeInTheDocument();
    expect(screen.getByText(/Findings: network/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^activate$/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    expect(approve).toHaveBeenCalledWith("skill-useful-tdd-bbbbbbbbbbbb", true);
  });

  it("keeps Activate disabled for a malicious quarantined pack", async () => {
    renderWithEngineConnection(<SkillsPage
skillsClient={skillsClient({ list: async () => [malicious] })}
      />, engine("ready"));

    expect(await screen.findByText("malicious-exfil")).toBeInTheDocument();
    expect(screen.getByText(/Findings: secrets/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^activate$/i })).toBeDisabled();
  });
});
