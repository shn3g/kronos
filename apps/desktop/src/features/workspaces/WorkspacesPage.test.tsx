// SPDX-License-Identifier: AGPL-3.0-or-later

import { act, screen } from "@testing-library/react";
import { renderWithEngineConnection } from "../../engine/testUtils";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient, EngineConnectionState } from "../../engine/client";
import { WorkspacesPage, type RepositoriesClient } from "./WorkspacesPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function repos(listImpl?: RepositoriesClient["list"]): RepositoriesClient {
  return {
    list: listImpl ?? (async () => []),
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
  };
}

describe("WorkspacesPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => []);
    renderWithEngineConnection(<WorkspacesPage
repositoriesClient={repos(list)}
      />, engine("unavailable"));

    expect(await screen.findByRole("heading", { level: 1, name: "Workspaces" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add workspace/i })).not.toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("lists enrolled repositories and runs the Add workspace preview wizard", async () => {
    const user = userEvent.setup();
    const enrolled = {
      id: "repo_alpha",
      displayName: "alpha",
      realpath: "C:/tmp/alpha",
      origin: "https://github.com/acme/alpha.git",
      status: "active" as const,
    };
    const client: RepositoriesClient = {
      list: async () => [enrolled],
      get: async () => {
        throw new Error("get should not run");
      },
      inspect: async (path) => ({
        gitRoot: path,
        origin: "https://github.com/acme/alpha.git",
        currentBranch: "main",
        defaultBranch: "main",
        languages: ["python"],
        packageManagers: ["pip"],
        policy: { autonomy: { freeze: true } },
        preview: [
          {
            path: ".kronos/config.yaml",
            action: "add",
            content: "freeze: true\n",
            unifiedDiff: "--- /dev/null\n+++ b/.kronos/config.yaml\n+freeze: true\n",
          },
        ],
        wroteFiles: false,
        committed: false,
        pushed: false,
      }),
      enrol: async () => enrolled,
      pause: async () => ({ ...enrolled, status: "paused" }),
      disable: async () => ({ ...enrolled, status: "disabled" }),
      resume: async () => ({ ...enrolled, status: "active" }),
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
    };

    renderWithEngineConnection(<WorkspacesPage
repositoriesClient={client}
        pickFolder={async () => "C:/tmp/alpha"}
      />, engine("ready"));

    expect(await screen.findByText("alpha")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^add workspace$/i }));
    await user.click(screen.getByRole("button", { name: /choose folder/i }));
    expect(await screen.findByText(".kronos/config.yaml")).toBeInTheDocument();
    expect(screen.getByText(/preview only/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^enrol$/i }));
    expect(await screen.findAllByText("alpha")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /^pause$/i }));
    expect(await screen.findByText(/paused/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^resume$/i }));
    expect(await screen.findByText(/active/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^disable$/i }));
    expect(await screen.findByText(/disabled/i)).toBeInTheDocument();
  });

  it("opens a folder from the empty state", async () => {
    const user = userEvent.setup();
    const enrolled = {
      id: "repo_alpha",
      displayName: "alpha",
      realpath: "C:/tmp/alpha",
      origin: null,
      status: "active" as const,
    };
    const onFolderOpened = vi.fn();
    const client: RepositoriesClient = {
      ...repos(),
      enrol: async () => enrolled,
    };

    renderWithEngineConnection(
      <WorkspacesPage
        repositoriesClient={client}
        pickFolder={async () => "C:/tmp/alpha"}
        onFolderOpened={onFolderOpened}
      />,
      engine("ready"),
    );

    await user.click(await screen.findByRole("button", { name: /^open a folder$/i }));
    expect(onFolderOpened).toHaveBeenCalledWith(enrolled);
    expect(await screen.findByText("alpha")).toBeInTheDocument();
  });

  it("shows structured errors when opening a folder fails", async () => {
    const user = userEvent.setup();
    const client: RepositoriesClient = {
      ...repos(),
      enrol: async () => {
        throw new Error("not a git repository");
      },
    };

    renderWithEngineConnection(
      <WorkspacesPage
        repositoriesClient={client}
        pickFolder={async () => "C:/tmp/plain"}
      />,
      engine("ready"),
    );

    await user.click(await screen.findByRole("button", { name: /^open a folder$/i }));
    expect(await screen.findByText("not a git repository")).toBeInTheDocument();
  });

  it("shows Open a folder when the engine becomes ready without remounting", async () => {
    vi.useFakeTimers();
    try {
      let status: EngineConnectionState = { status: "unavailable" };
      const engineClient: EngineClient = {
        getState: async () => status,
      };
      renderWithEngineConnection(<WorkspacesPage
repositoriesClient={repos()} />, engineClient);
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText(/waiting for the engine/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /open a folder/i })).not.toBeInTheDocument();

      status = { status: "ready", version: "0.1.0" };
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
      expect(screen.getByRole("button", { name: /^open a folder$/i })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("previews a typed folder path without injecting a picker", async () => {
    const user = userEvent.setup();
    const client: RepositoriesClient = {
      list: async () => [],
      get: async () => {
        throw new Error("get should not run");
      },
      inspect: async (path) => ({
        gitRoot: path,
        origin: null,
        currentBranch: "main",
        defaultBranch: "main",
        languages: ["python"],
        packageManagers: ["pip"],
        policy: { autonomy: { freeze: true } },
        preview: [
          {
            path: ".kronos/config.yaml",
            action: "add",
            content: "freeze: true\n",
            unifiedDiff: "+freeze: true\n",
          },
        ],
        wroteFiles: false,
        committed: false,
        pushed: false,
      }),
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
    };

    renderWithEngineConnection(<WorkspacesPage
repositoriesClient={client} />, engine("ready"));

    await user.click(await screen.findByRole("button", { name: /^add workspace$/i }));
    await user.type(screen.getByLabelText(/repository folder/i), "C:/tmp/typed");
    await user.click(screen.getByRole("button", { name: /preview/i }));
    expect(await screen.findByText(".kronos/config.yaml")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/repository folder/i), "-edit");
    expect(screen.queryByText(".kronos/config.yaml")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("heading", { name: /add workspace/i })).not.toBeInTheDocument();
  });
});
