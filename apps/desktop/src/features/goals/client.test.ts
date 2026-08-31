/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionGoalsClient } from "./client";

describe("createProductionGoalsClient", () => {
  it("lists goals through the engine JSON proxy", async () => {
    const client = createProductionGoalsClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/goals");
      return {
        status: 200,
        body: JSON.stringify({
          goals: [
            {
              id: "goal_1",
              repository_id: "repo_alpha",
              title: "Fix add",
              state: "draft",
              source: "desktop",
              risk_ceiling: "low",
              success_criteria: "pass",
              non_goals: "scope",
              stop_reason: null,
            },
          ],
        }),
      };
    });

    await expect(client.list()).resolves.toEqual([
      {
        id: "goal_1",
        repositoryId: "repo_alpha",
        title: "Fix add",
        state: "draft",
        source: "desktop",
        riskCeiling: "low",
        successCriteria: "pass",
        nonGoals: "scope",
        stopReason: null,
        schedule: null,
      },
    ]);
  });
});
