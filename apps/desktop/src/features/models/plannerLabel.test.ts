// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { plannerDisplayName } from "./plannerLabel";

describe("plannerDisplayName", () => {
  it("returns the assigned planner profile name", () => {
    expect(
      plannerDisplayName({
        detected: [],
        profiles: [{ id: "prof_local", displayName: "Local llama", role: "planner", billed: false }],
        assignments: {
          planner: "prof_local",
          coder: "prof_local",
          reviewer: "prof_local",
          embedding: "prof_local",
        },
      }),
    ).toBe("Local llama");
  });

  it("returns null when no planner is assigned", () => {
    expect(
      plannerDisplayName({
        detected: [],
        profiles: [],
        assignments: {
          planner: null,
          coder: null,
          reviewer: null,
          embedding: null,
        },
      }),
    ).toBeNull();
  });
});
