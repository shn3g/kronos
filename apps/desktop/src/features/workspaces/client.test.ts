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

  it("writes a workspace file through PUT /repositories/{id}/files/contents", async () => {
    const client = createProductionRepositoriesClient(async (method, path, body) => {
      expect(method).toBe("PUT");
      expect(path).toBe("/repositories/repo_alpha/files/contents");
      expect(body).toEqual({ path: "src/ok.ts", content: "const ok = false;" });
      return { status: 200, body: JSON.stringify({ path: "src/ok.ts", ok: true }) };
    });

    await expect(client.writeFile("repo_alpha", "src/ok.ts", "const ok = false;")).resolves.toBeUndefined();
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

  it("writes a workspace file through writeWorkspaceFile", async () => {
    const client = createProductionRepositoriesClient(async (method, path, body) => {
      expect(method).toBe("PUT");
      expect(path).toBe("/repositories/repo_alpha/files/contents");
      expect(body).toEqual({ path: "src/ok.ts", content: "const ok = false;" });
      return { status: 200, body: JSON.stringify({ path: "src/ok.ts", ok: true }) };
    });

    await expect(
      client.writeWorkspaceFile("repo_alpha", "src/ok.ts", "const ok = false;"),
    ).resolves.toBeUndefined();
  });
});
