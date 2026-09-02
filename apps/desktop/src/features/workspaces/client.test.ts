/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionRepositoriesClient } from "./client";

describe("createProductionRepositoriesClient", () => {
  it("maps enrolled repositories from the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories");
      return {
        status: 200,
        body: JSON.stringify({
          repositories: [
            {
              id: "repo_alpha",
              display_name: "alpha",
              realpath: "C:/tmp/alpha",
              origin: "https://github.com/acme/alpha.git",
              status: "paused",
            },
          ],
        }),
      };
    });

    await expect(client.list()).resolves.toEqual([
      {
        id: "repo_alpha",
        displayName: "alpha",
        realpath: "C:/tmp/alpha",
        origin: "https://github.com/acme/alpha.git",
        status: "paused",
      },
    ]);
  });

  it("resumes a paused repository through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/resume");
      return {
        status: 200,
        body: JSON.stringify({
          repository: {
            id: "repo_alpha",
            display_name: "alpha",
            realpath: "C:/tmp/alpha",
            origin: "https://github.com/acme/alpha.git",
            status: "active",
          },
        }),
      };
    });

    await expect(client.resume("repo_alpha")).resolves.toEqual({
      id: "repo_alpha",
      displayName: "alpha",
      realpath: "C:/tmp/alpha",
      origin: "https://github.com/acme/alpha.git",
      status: "active",
    });
  });

  it("lists working-tree changes from the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories/repo_alpha/changes");
      return {
        status: 200,
        body: JSON.stringify({
          changes: [
            {
              path: "src/App.tsx",
              summary: "Modified src/App.tsx",
              patch: "-old\n+new\n",
              status: "M",
              from_chat: true,
            },
          ],
        }),
      };
    });

    await expect(client.listChanges("repo_alpha")).resolves.toEqual([
      {
        path: "src/App.tsx",
        summary: "Modified src/App.tsx",
        patch: "-old\n+new\n",
        status: "M",
        fromChat: true,
      },
    ]);
  });
});
