// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { checksFromLocal } from "./checks";

describe("checksFromLocal", () => {
  it("never uses color-only status and names every check", () => {
    const checks = checksFromLocal({
      engineReady: true,
      modelReady: false,
      workspaceReady: false,
      indexReady: true,
    });
    expect(checks.map((item) => item.id)).toEqual([
      "engine",
      "model",
      "workspace",
      "index",
      "secrets",
    ]);
    expect(checks[0]?.ok).toBe(true);
    expect(checks[1]?.ok).toBe(false);
    expect(checks[1]?.detail.toLowerCase()).toContain("connect an orchestrator");
    expect(checks[1]?.detail.toLowerCase()).not.toContain("planner");
    expect(checks[4]?.ok).toBe(true);
  });

  it("says an orchestrator is assigned when the model is ready", () => {
    const [model] = checksFromLocal({
      engineReady: true,
      modelReady: true,
      workspaceReady: true,
      indexReady: true,
    }).filter((item) => item.id === "model");
    expect(model?.ok).toBe(true);
    expect(model?.detail).toBe("An orchestrator model is assigned.");
  });
});
