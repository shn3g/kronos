// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../../engine/client";
import { GitHubPage, type GitHubClient } from "./GitHubPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function githubClient(overrides: Partial<GitHubClient> = {}): GitHubClient {
  return {
    status: async () => ({
      controller: { registered: false, installed: false, verified: false },
      reviewer: { registered: false, installed: false, verified: false },
      webhookEnabled: false,
      pollMode: "conditional",
      githubCliPresent: false,
    }),
    manifests: async () => ({
      controller: { name: "Kronos Controller" },
      reviewer: { name: "Kronos Reviewer" },
      reviewerCheckName: "kronos-review (kronos-reviewer)",
    }),
    registerApp: async () => ({ role: "controller", registered: true }),
    recordInstallation: async () => ({ role: "controller", installed: true }),
    verify: async () => ({ role: "controller", verified: true }),
    proposeRuleset: async () => ({
      strict: true,
      requiredChecks: [
        { context: "kronos-review (kronos-reviewer)", integrationId: 1002 },
      ],
    }),
    applyRuleset: async () => ({ applied: true }),
    ...overrides,
  };
}

describe("GitHubPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const status = vi.fn(async () => githubClient().status());
    render(
      <GitHubPage engineClient={engine("unavailable")} githubClient={githubClient({ status })} />,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Connections" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to create and install GitHub Apps/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save controller app/i })).not.toBeInTheDocument();
    expect(status).not.toHaveBeenCalled();
  });

  it("guides create install and verify for both Apps", async () => {
    const user = userEvent.setup();
    const registerApp = vi.fn(async () => ({ role: "controller", registered: true }));
    const recordInstallation = vi.fn(async () => ({ role: "controller", installed: true }));
    const verify = vi.fn(async () => ({ role: "controller", verified: true }));
    render(
      <GitHubPage
        engineClient={engine("ready")}
        githubClient={githubClient({ registerApp, recordInstallation, verify })}
      />,
    );

    expect(await screen.findByRole("heading", { name: /controller app/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /reviewer app/i })).toBeInTheDocument();
    expect(screen.getByText("kronos-review (kronos-reviewer)")).toBeInTheDocument();
    expect(screen.getByText(/webhooks are off/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/controller app id/i), "1001");
    await user.type(screen.getByLabelText(/controller slug/i), "kronos-controller");
    await user.type(screen.getByLabelText(/controller private key/i), "-----BEGIN RSA PRIVATE KEY-----");
    await user.click(screen.getByRole("button", { name: /save controller app/i }));
    expect(registerApp).toHaveBeenCalled();

    await user.type(screen.getByLabelText(/controller installation id/i), "2001");
    await user.click(screen.getByRole("button", { name: /save controller installation/i }));
    expect(recordInstallation).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /verify controller/i }));
    expect(verify).toHaveBeenCalled();
  });

  it("requires operator confirmation before applying a ruleset", async () => {
    const user = userEvent.setup();
    const applyRuleset = vi.fn(async () => ({ applied: true }));
    render(
      <GitHubPage engineClient={engine("ready")} githubClient={githubClient({ applyRuleset })} />,
    );

    expect(await screen.findByRole("button", { name: /apply ruleset/i })).toBeDisabled();
    await user.click(screen.getByLabelText(/i confirm this does not weaken existing protections/i));
    expect(screen.getByRole("button", { name: /apply ruleset/i })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /apply ruleset/i }));
    expect(applyRuleset).toHaveBeenCalled();
  });
});
