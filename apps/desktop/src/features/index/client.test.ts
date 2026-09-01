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
          state: "embedding",
          files_done: 3,
          files_total: 8,
          chunks_embedded: 10,
          chunks_skipped: 2,
          last_activity_at: "2026-09-01T15:00:00+00:00",
          watch_enabled: true,
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
      state: "embedding",
      filesDone: 3,
      filesTotal: 8,
      chunksEmbedded: 10,
      chunksSkipped: 2,
      lastActivityAt: "2026-09-01T15:00:00+00:00",
      watchEnabled: true,
    });
  });

  it("toggles watch through the engine JSON proxy", async () => {
    const client = createProductionIndexClient(async (method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/index/watch");
      expect(body).toEqual({ enabled: false });
      return {
        status: 200,
        body: JSON.stringify({
          repository_id: "repo_alpha",
          commit: "abc123",
          chunk_count: 12,
          dense_available: false,
          index_path: "C:/cache/indexes/repo_alpha",
          ready: true,
          state: "idle",
          files_done: 8,
          files_total: 8,
          chunks_embedded: 10,
          chunks_skipped: 2,
          last_activity_at: "2026-09-01T15:00:00+00:00",
          watch_enabled: false,
        }),
      };
    });

    await expect(client.setWatch("repo_alpha", false)).resolves.toMatchObject({
      watchEnabled: false,
      state: "idle",
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
