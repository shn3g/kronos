// SPDX-License-Identifier: AGPL-3.0-or-later

import { screen } from "@testing-library/react";
import { renderWithEngineConnection } from "../../../engine/testUtils";
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
      controller: {
        registered: false,
        installed: false,
        verified: false,
        appId: null,
        slug: null,
        createUrl: "https://github.com/settings/apps/new",
        installUrl: null,
      },
      reviewer: {
        registered: true,
        installed: true,
        verified: true,
        appId: 9001,
        slug: "kronos-reviewer",
        createUrl: "https://github.com/settings/apps/new",
        installUrl: "https://github.com/apps/kronos-reviewer/installations/new",
      },
      webhookEnabled: false,
      pollMode: "conditional",
      githubCliPresent: false,
      enrolled: {
        owner: "widgets",
        repo: "shop",
        integrationBranch: "integration",
        protectedBranch: "main",
        repositoryId: "repo_shop",
      },
    }),
    manifests: async () => ({
      controller: { name: "Kronos Controller" },
      reviewer: { name: "Kronos Reviewer" },
      reviewerCheckName: "kronos-review (kronos-reviewer)",
    }),
    convertManifest: async () => ({ role: "controller", registered: true, appId: 1001, slug: "kronos-controller" }),
    recordInstallation: async () => ({ role: "controller", installed: true }),
    verify: async () => ({ role: "controller", verified: true }),
    proposeRuleset: async () => ({
      strict: true,
      requiredChecks: [{ context: "kronos-review (kronos-reviewer)", integrationId: 9001 }],
    }),
    applyRuleset: async () => ({ applied: true }),
    safety: async () => ({
      ok: false,
      checks: [
        { id: "ruleset_strict", ok: false, detail: "ruleset is not strict" },
        { id: "kronos_pr_workflow", ok: false, detail: "workflow missing" },
        { id: "codeowners", ok: false, detail: "CODEOWNERS missing" },
        { id: "reviewer_app", ok: false, detail: "reviewer is not verified" },
      ],
    }),
    ...overrides,
  };
}

describe("GitHubPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const status = vi.fn(async () => githubClient().status());
    renderWithEngineConnection(<GitHubPage
githubClient={githubClient({ status })} />, engine("unavailable"));

    expect(await screen.findByRole("heading", { level: 1, name: "Connections" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /convert controller/i })).not.toBeInTheDocument();
    expect(status).not.toHaveBeenCalled();
  });

  it("guides create install and verify for both Apps without a PEM field", async () => {
    const user = userEvent.setup();
    const convertManifest = vi.fn(async () => ({
      role: "controller",
      registered: true,
      appId: 1001,
      slug: "kronos-controller",
    }));
    const recordInstallation = vi.fn(async () => ({ role: "controller", installed: true }));
    const verify = vi.fn(async () => ({ role: "controller", verified: true }));
    const status = vi.fn(async () => ({
      ...(await githubClient().status()),
      controller: {
        registered: true,
        installed: true,
        verified: true,
        appId: 1001,
        slug: "kronos-controller",
        createUrl: "https://github.com/settings/apps/new",
        installUrl: "https://github.com/apps/kronos-controller/installations/new",
      },
    }));
    renderWithEngineConnection(<GitHubPage
githubClient={githubClient({ convertManifest, recordInstallation, verify, status })}
      />, engine("ready"));

    expect(await screen.findByRole("heading", { name: /controller app/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /reviewer app/i })).toBeInTheDocument();
    expect(screen.getByText("kronos-review (kronos-reviewer)")).toBeInTheDocument();
    expect(screen.getByText(/webhooks are off/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/private key/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /create .* on github/i }).length).toBeGreaterThan(0);

    await user.type(screen.getByLabelText(/controller manifest code/i), "controller-manifest");
    await user.click(screen.getByRole("button", { name: /convert controller/i }));
    expect(convertManifest).toHaveBeenCalledWith("controller", "controller-manifest");

    await user.type(screen.getByLabelText(/controller installation id/i), "2001");
    await user.click(screen.getByRole("button", { name: /save controller installation/i }));
    expect(recordInstallation).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /verify controller/i }));
    expect(verify).toHaveBeenCalled();
    expect(await screen.findByText(/app id:\s*1001/i)).toBeInTheDocument();
    expect(screen.getByText(/slug:\s*kronos-controller/i)).toBeInTheDocument();
    expect(screen.getAllByText(/registered:\s*yes/i).length).toBeGreaterThan(0);
  });

  it("proposes then applies the enrolled origin with operator confirmation", async () => {
    const user = userEvent.setup();
    const proposeRuleset = vi.fn(async () => ({
      strict: true,
      requiredChecks: [{ context: "kronos-review (kronos-reviewer)", integrationId: 9001 }],
    }));
    const applyRuleset = vi.fn(async () => ({ applied: true }));
    renderWithEngineConnection(<GitHubPage
githubClient={githubClient({ proposeRuleset, applyRuleset })}
      />, engine("ready"));

    expect(await screen.findByText(/widgets\/shop/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/kronos-review \(kronos-reviewer\)/i)).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/strict:\s*yes/i)).toBeInTheDocument();
    expect(proposeRuleset).toHaveBeenCalledWith({
      owner: "widgets",
      repo: "shop",
      reviewerIntegrationId: 9001,
      integrationBranch: "integration",
    });

    expect(screen.getByRole("button", { name: /apply ruleset/i })).toBeDisabled();
    await user.click(screen.getByLabelText(/i confirm this does not weaken existing protections/i));
    expect(screen.getByRole("button", { name: /apply ruleset/i })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /apply ruleset/i }));
    expect(applyRuleset).toHaveBeenCalledWith({
      owner: "widgets",
      repo: "shop",
      reviewerIntegrationId: 9001,
      integrationBranch: "integration",
      confirm: true,
    });
  });

  it("lists safety checks and shows elevation blocked when safety is not ok", async () => {
    const safety = vi.fn(async () => ({
      ok: false,
      checks: [
        { id: "ruleset_strict", ok: false, detail: "ruleset is not strict" },
        { id: "kronos_pr_workflow", ok: true, detail: "present" },
        { id: "codeowners", ok: false, detail: "CODEOWNERS missing" },
        { id: "reviewer_app", ok: false, detail: "reviewer is not verified" },
      ],
    }));
    renderWithEngineConnection(<GitHubPage
githubClient={githubClient({ safety })} />, engine("ready"));

    expect(await screen.findByText(/widgets\/shop/i)).toBeInTheDocument();
    expect(await screen.findByText(/ruleset_strict/i)).toBeInTheDocument();
    expect(screen.getByText(/kronos_pr_workflow/i)).toBeInTheDocument();
    expect(screen.getByText(/codeowners/i)).toBeInTheDocument();
    expect(screen.getByText(/reviewer_app/i)).toBeInTheDocument();
    expect(screen.getByText(/elevation is blocked/i)).toBeInTheDocument();
    expect(safety).toHaveBeenCalledWith("repo_shop");
  });

  it("fails closed when safety cannot be loaded", async () => {
    const safety = vi.fn(async () => {
      throw new Error("engine request failed: 0");
    });
    renderWithEngineConnection(<GitHubPage
githubClient={githubClient({ safety })} />, engine("ready"));

    expect(await screen.findByText(/widgets\/shop/i)).toBeInTheDocument();
    expect(await screen.findByText(/elevation is blocked/i)).toBeInTheDocument();
    expect(safety).toHaveBeenCalled();
  });
});
