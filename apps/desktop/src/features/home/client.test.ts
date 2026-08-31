/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionHomeClient } from "./client";

describe("createProductionHomeClient", () => {
  it("loads the dashboard through the engine JSON proxy", async () => {
    const calls: string[] = [];
    const client = createProductionHomeClient(async (method, path) => {
      calls.push(`${method} ${path}`);
      return {
        status: 200,
        body: JSON.stringify({
          ready: true,
          repositories: [{ id: "repo_alpha", display_name: "alpha", realpath: "C:/tmp/alpha" }],
          schedules: [{ id: "goal_1", title: "Nightly scan", schedule: "0 4 * * *" }],
          budgets: [{ repository_id: "repo_alpha", attempts: 1, breaker_open: false }],
          runs: [{ id: "run_1", status: "succeeded", evidence: "tests/test_repro.py" }],
          diffs: [{ path: "pkg/math.py", summary: "+2 -1" }],
          tests: [{ name: "pytest", passed: true }],
          index: [{ repository_id: "repo_alpha", ready: true, dense_available: false, chunk_count: 4 }],
        }),
      };
    });
    const dash = await client.dashboard();
    expect(calls).toEqual(["GET /ops/dashboard"]);
    expect(dash.ready).toBe(true);
    expect(dash.schedules[0]?.title).toBe("Nightly scan");
    expect(dash.index[0]?.denseAvailable).toBe(false);
  });
});
