/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionGitHubClient } from "./client";

describe("createProductionGitHubClient", () => {
  it("loads status and manifests through the engine JSON proxy", async () => {
    const calls: string[] = [];
    const client = createProductionGitHubClient(async (method, path) => {
      calls.push(`${method} ${path}`);
      if (path === "/github/status") {
        return {
          status: 200,
          body: JSON.stringify({
            controller: { registered: true, installed: true, verified: true },
            reviewer: { registered: false, installed: false, verified: false },
            webhook_enabled: false,
            poll_mode: "conditional",
            github_cli_present: true,
            enrolled: {
              owner: "widgets",
              repo: "shop",
              integration_branch: "integration",
              protected_branch: "main",
            },
          }),
        };
      }
      return {
        status: 200,
        body: JSON.stringify({
          controller: { name: "Kronos Controller" },
          reviewer: { name: "Kronos Reviewer" },
          reviewer_check_name: "kronos-review (kronos-reviewer)",
        }),
      };
    });

    await expect(client.status()).resolves.toEqual({
      controller: {
        registered: true,
        installed: true,
        verified: true,
        appId: null,
        slug: null,
        createUrl: "",
        installUrl: null,
      },
      reviewer: {
        registered: false,
        installed: false,
        verified: false,
        appId: null,
        slug: null,
        createUrl: "",
        installUrl: null,
      },
      webhookEnabled: false,
      pollMode: "conditional",
      githubCliPresent: true,
      enrolled: {
        owner: "widgets",
        repo: "shop",
        integrationBranch: "integration",
        protectedBranch: "main",
      },
    });
    await expect(client.manifests()).resolves.toEqual({
      controller: { name: "Kronos Controller" },
      reviewer: { name: "Kronos Reviewer" },
      reviewerCheckName: "kronos-review (kronos-reviewer)",
    });
    expect(calls).toEqual(["GET /github/status", "GET /github/manifests"]);
  });

  it("converts a manifest code without sending a private key", async () => {
    const bodies: unknown[] = [];
    const client = createProductionGitHubClient(async (method, path, body) => {
      bodies.push({ method, path, body });
      return {
        status: 200,
        body: JSON.stringify({
          role: "controller",
          registered: true,
          app_id: 1001,
          slug: "kronos-controller",
        }),
      };
    });
    await expect(client.convertManifest("controller", "controller-manifest")).resolves.toEqual({
      role: "controller",
      registered: true,
      appId: 1001,
      slug: "kronos-controller",
    });
    expect(bodies).toEqual([
      {
        method: "POST",
        path: "/github/apps/controller/convert",
        body: { code: "controller-manifest" },
      },
    ]);
    expect(JSON.stringify(bodies)).not.toMatch(/BEGIN RSA|private_key/i);
  });

  it("fails closed when the engine proxy is unavailable", async () => {
    const client = createProductionGitHubClient(async () => ({ status: 0, body: "" }));
    await expect(client.status()).rejects.toThrow(/engine/i);
  });
});
