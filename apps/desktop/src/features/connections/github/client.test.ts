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
      controller: { registered: true, installed: true, verified: true },
      reviewer: { registered: false, installed: false, verified: false },
      webhookEnabled: false,
      pollMode: "conditional",
      githubCliPresent: true,
    });
    await expect(client.manifests()).resolves.toEqual({
      controller: { name: "Kronos Controller" },
      reviewer: { name: "Kronos Reviewer" },
      reviewerCheckName: "kronos-review (kronos-reviewer)",
    });
    expect(calls).toEqual(["GET /github/status", "GET /github/manifests"]);
  });

  it("fails closed when the engine proxy is unavailable", async () => {
    const client = createProductionGitHubClient(async () => ({ status: 0, body: "" }));
    await expect(client.status()).rejects.toThrow(/engine/i);
  });
});
