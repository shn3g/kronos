/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionModelsClient } from "./client";

describe("createProductionModelsClient", () => {
  it("maps assignments from the engine JSON proxy", async () => {
    const client = createProductionModelsClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/models");
      return {
        status: 200,
        body: JSON.stringify({
          detected: [{ kind: "cursor_cli", label: "cursor-agent", present: true }],
          profiles: [
            {
              id: "prof_local",
              display_name: "Local llama3",
              role: "coder",
              billed: false,
            },
          ],
          assignments: {
            planner: "prof_local",
            coder: "prof_local",
            reviewer: "prof_local",
            embedding: "prof_local",
          },
        }),
      };
    });

    await expect(client.snapshot()).resolves.toEqual({
      detected: [{ kind: "cursor_cli", label: "cursor-agent", present: true }],
      profiles: [{ id: "prof_local", displayName: "Local llama3", role: "coder", billed: false }],
      assignments: {
        planner: "prof_local",
        coder: "prof_local",
        reviewer: "prof_local",
        embedding: "prof_local",
      },
    });
  });

  it("saves role assignments through the engine JSON proxy", async () => {
    const client = createProductionModelsClient(async (method, path, body) => {
      expect(method).toBe("PUT");
      expect(path).toBe("/models/assignments");
      expect(body).toEqual({
        planner: "prof_a",
        coder: "prof_a",
        reviewer: "prof_a",
        embedding: "prof_b",
      });
      return {
        status: 200,
        body: JSON.stringify({
          assignments: {
            planner: "prof_a",
            coder: "prof_a",
            reviewer: "prof_a",
            embedding: "prof_b",
          },
        }),
      };
    });

    await expect(
      client.assign({
        planner: "prof_a",
        coder: "prof_a",
        reviewer: "prof_a",
        embedding: "prof_b",
      }),
    ).resolves.toEqual({
      planner: "prof_a",
      coder: "prof_a",
      reviewer: "prof_a",
      embedding: "prof_b",
    });
  });
});
