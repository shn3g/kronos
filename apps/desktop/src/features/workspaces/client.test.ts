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

  it("reverts a chat write through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/writes/revert");
      expect(body).toEqual({ path: "src/App.tsx" });
      return { status: 200, body: JSON.stringify({ ok: true, path: "src/App.tsx" }) };
    });

    await expect(client.revertWrite("repo_alpha", "src/App.tsx")).resolves.toBeUndefined();
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

  it("commits working-tree paths through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/commits");
      expect(body).toEqual({ message: "Fix App", paths: ["src/App.tsx"] });
      return { status: 200, body: JSON.stringify({ ok: true, sha: "abc", paths: ["src/App.tsx"] }) };
    });

    await expect(
      client.commitFiles("repo_alpha", "Fix App", ["src/App.tsx"]),
    ).resolves.toBeUndefined();
  });

  it("lists workspace files from the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories/repo_alpha/files");
      return {
        status: 200,
        body: JSON.stringify({ files: [{ path: "src/app.py" }, { path: "README.md" }] }),
      };
    });

    await expect(client.listWorkspaceFiles("repo_alpha")).resolves.toEqual([
      { path: "src/app.py" },
      { path: "README.md" },
    ]);
  });

  it("reads a workspace file through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories/repo_alpha/files/contents?path=src%2Fapp.py");
      return {
        status: 200,
        body: JSON.stringify({ path: "src/app.py", content: "print(1)\n", binary: false }),
      };
    });

    await expect(client.readWorkspaceFile("repo_alpha", "src/app.py")).resolves.toEqual({
      path: "src/app.py",
      content: "print(1)\n",
      binary: false,
    });
  });
});
