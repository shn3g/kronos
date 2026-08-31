/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionRunsClient } from "./client";

describe("createProductionRunsClient", () => {
  it("lists runs through the engine JSON proxy", async () => {
    const client = createProductionRunsClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/runs");
      return {
        status: 200,
        body: JSON.stringify({
          runs: [
            {
              id: "run_1",
              goal_id: "goal_1",
              task_id: "task_add",
              status: "succeeded",
              evidence: "tests/test_repro.py",
              pr_url: "https://github.com/acme/app/pull/1",
            },
          ],
        }),
      };
    });

    await expect(client.list()).resolves.toEqual([
      {
        id: "run_1",
        goalId: "goal_1",
        taskId: "task_add",
        status: "succeeded",
        evidence: "tests/test_repro.py",
        prUrl: "https://github.com/acme/app/pull/1",
      },
    ]);
  });
});
