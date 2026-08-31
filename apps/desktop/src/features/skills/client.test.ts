/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionSkillsClient } from "./client";

describe("createProductionSkillsClient", () => {
  it("lists skills through the engine JSON proxy", async () => {
    const client = createProductionSkillsClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/skills");
      return {
        status: 200,
        body: JSON.stringify({
          skills: [
            {
              id: "skill-tdd-core",
              name: "tdd",
              revision: "a".repeat(40),
              locator: "bundled",
              status: "active",
              scope: "core",
              description: "Write a failing test first.",
              capabilities: ["tdd"],
              scan: {
                malicious: false,
                executed_scripts: false,
                files: ["SKILL.md"],
                scripts: [],
                declared_permissions: ["worktree_write"],
                findings: [{ path: "SKILL.md", code: "network", detail: "urllib" }],
              },
            },
          ],
        }),
      };
    });

    await expect(client.list()).resolves.toEqual([
      {
        id: "skill-tdd-core",
        name: "tdd",
        revision: "a".repeat(40),
        locator: "bundled",
        status: "active",
        scope: "core",
        description: "Write a failing test first.",
        capabilities: ["tdd"],
        scan: {
          malicious: false,
          executedScripts: false,
          files: ["SKILL.md"],
          scripts: [],
          permissions: ["worktree_write"],
          findings: [{ path: "SKILL.md", code: "network", detail: "urllib" }],
        },
      },
    ]);
  });

  it("fails closed when the engine proxy is unavailable", async () => {
    const client = createProductionSkillsClient(async () => ({ status: 0, body: "" }));
    await expect(client.list()).rejects.toThrow(/engine request failed: 0/);
  });
});
