/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionIndexClient } from "./client";

describe("createProductionIndexClient", () => {
  it("loads index status through the engine JSON proxy", async () => {
    const client = createProductionIndexClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories/repo_alpha/index");
      return {
        status: 200,
        body: JSON.stringify({
          repository_id: "repo_alpha",
          commit: "abc123",
          chunk_count: 12,
          dense_available: false,
          index_path: "C:/cache/indexes/repo_alpha",
          ready: true,
        }),
      };
    });

    await expect(client.status("repo_alpha")).resolves.toEqual({
      repositoryId: "repo_alpha",
      commit: "abc123",
      chunkCount: 12,
      denseAvailable: false,
      indexPath: "C:/cache/indexes/repo_alpha",
      ready: true,
    });
  });

  it("searches through the engine JSON proxy", async () => {
    const client = createProductionIndexClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories/repo_alpha/index/search?q=connect");
      return {
        status: 200,
        body: JSON.stringify({
          items: [
            {
              path: "pkg/db.py",
              start_line: 1,
              end_line: 4,
              commit: "abc123",
              symbol: "connect",
              rank_sources: ["sparse", "graph"],
              trust: "tracked",
              text: "def connect",
            },
          ],
        }),
      };
    });

    await expect(client.search("repo_alpha", "connect")).resolves.toEqual([
      {
        path: "pkg/db.py",
        startLine: 1,
        endLine: 4,
        commit: "abc123",
        symbol: "connect",
        rankSources: ["sparse", "graph"],
        trust: "tracked",
        text: "def connect",
      },
    ]);
  });

  it("fails closed when the engine proxy returns a non-success status", async () => {
    const client = createProductionIndexClient(async () => ({ status: 0, body: "" }));
    await expect(client.status("repo_alpha")).rejects.toThrow(/engine request failed/i);
  });
});
