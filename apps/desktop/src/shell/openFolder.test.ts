// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it, vi } from "vitest";
import type { EnrolledRepository, RepositoriesClient } from "../features/workspaces/client";
import { findRepositoryByPath, openRepositoryFolder } from "./openFolder";

function repo(id: string, realpath: string): EnrolledRepository {
  return {
    id,
    displayName: id,
    realpath,
    origin: null,
    status: "active",
  };
}

function client(overrides: Partial<RepositoriesClient> = {}): RepositoriesClient {
  return {
    list: async () => [],
    get: async () => {
      throw new Error("get should not run");
    },
    inspect: async () => {
      throw new Error("inspect should not run");
    },
    enrol: async () => {
      throw new Error("enrol should not run");
    },
    pause: async () => {
      throw new Error("pause should not run");
    },
    disable: async () => {
      throw new Error("disable should not run");
    },
    resume: async () => {
      throw new Error("resume should not run");
    },
    listChanges: async () => [],
    listWorkspaceFiles: async () => [],
    readWorkspaceFile: async () => ({ path: "", content: "", binary: false }),
    writeFile: async () => undefined,
    writeWorkspaceFile: async () => undefined,
    revertWrite: async () => undefined,
    commitFiles: async () => undefined,
    runWorkspaceCommand: async () => {
      throw new Error("runWorkspaceCommand should not run");
    },
    startWorkspaceShell: async () => {
      throw new Error("startWorkspaceShell should not run");
    },
    writeWorkspaceShell: async () => ({ ok: true }),
    resizeWorkspaceShell: async () => ({ ok: true }),
    watchWorkspaceCommand: async () => ({
      command: "",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: false,
      output: "",
    }),
    cancelWorkspaceCommand: async () => ({ ok: true }),
    ...overrides,
  };
}

describe("findRepositoryByPath", () => {
  it("matches paths regardless of separators and trailing slashes", () => {
    const listed = [repo("repo_alpha", "C:/tmp/alpha")];
    expect(findRepositoryByPath(listed, "C:\\tmp\\alpha\\")).toEqual(listed[0]);
    expect(findRepositoryByPath(listed, "C:/tmp/bravo")).toBeNull();
  });
});

describe("openRepositoryFolder", () => {
  it("returns null when the picker is cancelled", async () => {
    const result = await openRepositoryFolder(client(), {
      pickFolder: async () => null,
    });
    expect(result).toBeNull();
  });

  it("reuses an already enrolled repository", async () => {
    const enrolled = repo("repo_alpha", "C:/tmp/alpha");
    const enrol = vi.fn();
    const result = await openRepositoryFolder(
      client({
        list: async () => [enrolled],
        enrol,
      }),
      {
        pickFolder: async () => "C:\\tmp\\alpha",
        repositories: [enrolled],
      },
    );

    expect(result).toEqual({ repository: enrolled, alreadyEnrolled: true });
    expect(enrol).not.toHaveBeenCalled();
  });

  it("enrols a new folder and surfaces structured client errors", async () => {
    const enrolled = repo("repo_bravo", "C:/tmp/bravo");
    const result = await openRepositoryFolder(
      client({
        enrol: async () => enrolled,
      }),
      {
        pickFolder: async () => "C:/tmp/bravo",
        repositories: [],
      },
    );

    expect(result).toEqual({ repository: enrolled, alreadyEnrolled: false });
  });

  it("propagates enrol failures from the repositories client", async () => {
    await expect(
      openRepositoryFolder(
        client({
          enrol: async () => {
            throw new Error("not a git repository");
          },
        }),
        {
          pickFolder: async () => "C:/tmp/plain",
          repositories: [],
        },
      ),
    ).rejects.toThrow("not a git repository");
  });
});
