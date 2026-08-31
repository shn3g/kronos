// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
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
    await user.click(screen.getByRole("button", { name: /^disable$/i }));
    expect(await screen.findByText(/disabled/i)).toBeInTheDocument();
  });
});
