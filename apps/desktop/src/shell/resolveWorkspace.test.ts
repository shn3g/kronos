import { describe, expect, it } from "vitest";
import type { EnrolledRepository } from "../features/workspaces/client";
import { resolveActiveWorkspaceId } from "./resolveWorkspace";

function repo(id: string, status: EnrolledRepository["status"] = "active"): EnrolledRepository {
  return {
    id,
    displayName: id,
    realpath: `/tmp/${id}`,
    origin: null,
    status,
  };
}

describe("resolveActiveWorkspaceId", () => {
  it("auto-picks the first active folder when nothing was stored", () => {
    expect(resolveActiveWorkspaceId([repo("alpha"), repo("beta")], null)).toBe("alpha");
  });

  it("honors an explicit empty choice", () => {
    expect(resolveActiveWorkspaceId([repo("alpha")], "")).toBeNull();
  });

  it("keeps a stored folder that is still active", () => {
    expect(resolveActiveWorkspaceId([repo("alpha"), repo("beta")], "beta")).toBe("beta");
  });

  it("falls back when the stored folder is gone or paused", () => {
    expect(resolveActiveWorkspaceId([repo("alpha")], "missing")).toBe("alpha");
    expect(resolveActiveWorkspaceId([repo("alpha", "paused")], "alpha")).toBeNull();
  });
});
