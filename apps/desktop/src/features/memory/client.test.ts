/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionMemoryClient } from "./client";

describe("createProductionMemoryClient", () => {
  it("lists records through the engine JSON proxy", async () => {
    const client = createProductionMemoryClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/memory");
      return {
        status: 200,
        body: JSON.stringify({
          records: [
            {
              id: "mem-1",
              kind: "episodic",
              text: "The reproduce test failed until the fence token was checked.",
              source_sha: "1".repeat(40),
              outcome: "helpful",
              confidence: 0.6,
              helpful: 1,
              harmful: 0,
              status: "proposed",
              skill_id: null,
            },
          ],
        }),
      };
    });

    await expect(client.list()).resolves.toEqual([
      {
        id: "mem-1",
        kind: "episodic",
        text: "The reproduce test failed until the fence token was checked.",
        sourceSha: "1".repeat(40),
        outcome: "helpful",
        confidence: 0.6,
        helpful: 1,
        harmful: 0,
        status: "proposed",
        skillId: null,
      },
    ]);
  });

  it("fails closed when the engine proxy is unavailable", async () => {
    const client = createProductionMemoryClient(async () => ({ status: 0, body: "" }));
    await expect(client.list()).rejects.toThrow(/engine request failed: 0/);
  });
});
