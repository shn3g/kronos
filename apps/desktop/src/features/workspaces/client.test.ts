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

  it("runs a workspace command through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/terminal/runs");
      expect(body).toEqual({ command: "python probe.py" });
      return {
        status: 200,
        body: JSON.stringify({
          command: "python probe.py",
          exit_code: 0,
          timed_out: false,
          output: "from-workspace\n",
        }),
      };
    });

    await expect(client.runWorkspaceCommand("repo_alpha", "python probe.py")).resolves.toEqual({
      command: "python probe.py",
      exitCode: 0,
      timedOut: false,
      cancelled: false,
      running: false,
      output: "from-workspace\n",
    });
  });

  it("stops a workspace command through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/terminal/runs/cancel");
      return {
        status: 200,
        body: JSON.stringify({ ok: true }),
      };
    });

    await expect(client.cancelWorkspaceCommand("repo_alpha")).resolves.toEqual({ ok: true });
  });

  it("reads live terminal output through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories/repo_alpha/terminal/runs");
      return {
        status: 200,
        body: JSON.stringify({
          command: "python stream.py",
          exit_code: null,
          timed_out: false,
          cancelled: false,
          running: true,
          output: "hello-live\n",
        }),
      };
    });

    await expect(client.watchWorkspaceCommand("repo_alpha")).resolves.toEqual({
      command: "python stream.py",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: "hello-live\n",
    });
  });

  it("starts a workspace shell through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/terminal/sessions");
      return {
        status: 200,
        body: JSON.stringify({
          command: "shell",
          exit_code: null,
          timed_out: false,
          cancelled: false,
          running: true,
          output: "",
        }),
      };
    });

    await expect(client.startWorkspaceShell("repo_alpha")).resolves.toEqual({
      command: "shell",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: "",
    });
  });

  it("sends a shell line through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/repositories/repo_alpha/terminal/sessions/input");
      expect(body).toEqual({ line: "echo hello-shell" });
      return {
        status: 200,
        body: JSON.stringify({ ok: true }),
      };
    });

    await expect(client.writeWorkspaceShell("repo_alpha", "echo hello-shell")).resolves.toEqual({
      ok: true,
    });
  });

  it("writes a workspace file through the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path, body) => {
      expect(method).toBe("PUT");
      expect(path).toBe("/repositories/repo_alpha/files/contents");
      expect(body).toEqual({ path: "src/ok.ts", content: "const ok = false;" });
      return {
        status: 200,
        body: JSON.stringify({ path: "src/ok.ts", ok: true }),
      };
    });

    await expect(
      client.writeWorkspaceFile("repo_alpha", "src/ok.ts", "const ok = false;"),
    ).resolves.toBeUndefined();
  });
});
