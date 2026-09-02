/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { hashFromRoute, routeFromHash } from "./routes";

describe("routeFromHash", () => {
  it("maps the five activities and settings sections", () => {
    expect(routeFromHash("#/chat")).toEqual({ activity: "chat", settingsSection: "general" });
    expect(routeFromHash("#/files")).toEqual({ activity: "files", settingsSection: "general" });
    expect(routeFromHash("#/goals")).toEqual({ activity: "goals", settingsSection: "general" });
    expect(routeFromHash("#/workspaces")).toEqual({
      activity: "workspaces",
      settingsSection: "general",
    });
    expect(routeFromHash("#/settings")).toEqual({
      activity: "settings",
      settingsSection: "general",
    });
    expect(routeFromHash("#/settings/models")).toEqual({
      activity: "settings",
      settingsSection: "models",
    });
  });

  it("rewrites legacy sidebar hashes into the settings hub", () => {
    expect(routeFromHash("#/models")).toEqual({
      activity: "settings",
      settingsSection: "models",
    });
    expect(routeFromHash("#/runs")).toEqual({ activity: "goals", settingsSection: "general" });
  });
});

describe("hashFromRoute", () => {
  it("writes activity and settings deep links", () => {
    expect(hashFromRoute({ activity: "chat", settingsSection: "general" })).toBe("#/chat");
    expect(hashFromRoute({ activity: "settings", settingsSection: "general" })).toBe("#/settings");
    expect(hashFromRoute({ activity: "settings", settingsSection: "models" })).toBe(
      "#/settings/models",
    );
  });
});
