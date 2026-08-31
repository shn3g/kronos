/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionGoalsClient } from "./client";

const goalPayload = {
  id: "goal_1",
  repository_id: "repo_alpha",
  title: "Fix add",
  state: "draft",
  source: "desktop",
  risk_ceiling: "low",
  success_criteria: "pass",
  non_goals: "scope",
  stop_reason: null,
  max_attempts: 3,
};

describe("createProductionGoalsClient", () => {
  it("lists goals through the engine JSON proxy", async () => {
    const client = createProductionGoalsClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/goals");
      return {
        status: 200,
        body: JSON.stringify({
          goals: [goalPayload],
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
        maxAttempts: 3,
      },
    ]);
  });

  it("plans a goal after create", async () => {
    const calls: string[] = [];
    const client = createProductionGoalsClient(async (method, path) => {
      calls.push(`${method} ${path}`);
      if (method === "POST" && path === "/goals") {
        return { status: 200, body: JSON.stringify({ ...goalPayload, id: "goal_new" }) };
      }
      if (method === "POST" && path === "/goals/goal_new/plan") {
        return {
          status: 200,
          body: JSON.stringify({
            goal: { ...goalPayload, id: "goal_new", state: "planned" },
            tasks: [
              {
                id: "task_add",
                goal_id: "goal_new",
                title: "fix add",
                state: "ready",
                kind: "implementation",
                stop_reason: null,
                pr_url: null,
                pr_base: null,
              },
            ],
          }),
        };
      }
      throw new Error(`unexpected ${method} ${path}`);
    });

    const created = await client.create({
      repositoryId: "repo_alpha",
      title: "Fix add",
      successCriteria: "pass",
      nonGoals: "scope",
      riskCeiling: "low",
      source: "desktop",
      maxAttempts: 3,
    });
    const planned = await client.plan(created.id);
    expect(calls).toEqual(["POST /goals", "POST /goals/goal_new/plan"]);
    expect(planned.goal.state).toBe("planned");
    expect(planned.tasks).toHaveLength(1);
  });

  it("ticks the goal engine", async () => {
    const client = createProductionGoalsClient(async (method, path) => {
      expect(method).toBe("POST");
      expect(path).toBe("/goals/tick");
      return {
        status: 200,
        body: JSON.stringify({
          ok: false,
          status: "plan_failed",
          reason: "index has no source path for evidence",
          task_id: null,
          pr_url: null,
          terminal: false,
        }),
      };
    });

    await expect(client.tick()).resolves.toEqual({
      ok: false,
      status: "plan_failed",
      reason: "index has no source path for evidence",
      taskId: null,
      prUrl: null,
      terminal: false,
    });
  });
});
