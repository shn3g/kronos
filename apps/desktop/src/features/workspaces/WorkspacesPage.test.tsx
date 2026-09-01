// SPDX-License-Identifier: AGPL-3.0-or-later

import { act, render, screen } from "@testing-library/react";
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
    revertWrite: async () => {
      throw new Error("revert should not run");
    },
  };
}

describe("WorkspacesPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => []);
    render(
      <WorkspacesPage
        engineClient={engine("unavailable")}
        repositoriesClient={repos(list)}
      />,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Workspaces" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to enrol repositories/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /enable kronos/i })).not.toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("lists enrolled repositories and runs the Enable Kronos preview wizard", async () => {
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
      revertWrite: async () => undefined,
    };

    render(
      <WorkspacesPage
        engineClient={engine("ready")}
        repositoriesClient={client}
        pickFolder={async () => "C:/tmp/alpha"}
      />,
    );

    expect(await screen.findByText("alpha")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /enable kronos/i }));
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

  it("shows Enable Kronos when the engine becomes ready without remounting", async () => {
    vi.useFakeTimers();
    try {
      let status: EngineConnectionState = { status: "unavailable" };
      const engineClient: EngineClient = {
        getState: async () => status,
      };
      render(
        <WorkspacesPage engineClient={engineClient} repositoriesClient={repos()} />,
      );
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText(/connect a compatible engine/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /enable kronos/i })).not.toBeInTheDocument();

      status = { status: "ready", version: "0.1.0" };
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
      expect(screen.getByRole("button", { name: /enable kronos/i })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("previews a typed folder path without injecting a picker", async () => {
    const user = userEvent.setup();
    const client: RepositoriesClient = {
      list: async () => [],
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
      revertWrite: async () => {
        throw new Error("revert should not run");
      },
    };

    render(<WorkspacesPage engineClient={engine("ready")} repositoriesClient={client} />);

    await user.click(await screen.findByRole("button", { name: /enable kronos/i }));
    await user.type(screen.getByLabelText(/repository folder/i), "C:/tmp/typed");
    await user.click(screen.getByRole("button", { name: /preview/i }));
    expect(await screen.findByText(".kronos/config.yaml")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/repository folder/i), "-edit");
    expect(screen.queryByText(".kronos/config.yaml")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("heading", { name: /enable kronos/i })).not.toBeInTheDocument();
  });
});
