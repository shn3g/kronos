// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import type { RepositoriesClient } from "../workspaces/client";
import { TerminalPage } from "./TerminalPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function unused(): Promise<never> {
  return Promise.reject(new Error("unused"));
}

function repos(overrides: Partial<RepositoriesClient> = {}): RepositoriesClient {
  return {
    list: async () => [],
    inspect: unused,
    enrol: unused,
    pause: unused,
    disable: unused,
    resume: unused,
    revertWrite: unused,
    listChanges: async () => [],
    commitFiles: unused,
    listWorkspaceFiles: async () => [],
    readWorkspaceFile: unused,
    runWorkspaceCommand: async () => ({
      command: "echo hi",
      exitCode: 0,
      timedOut: false,
      output: "hi\n",
    }),
    ...overrides,
  };
}

describe("TerminalPage", () => {
  it("stays closed when the engine is not ready", async () => {
    const runWorkspaceCommand = vi.fn();
    render(
      <TerminalPage
        engineClient={engine("unavailable")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ runWorkspaceCommand })}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("heading", { level: 2, name: "Terminal" })).toBeInTheDocument();
    expect(screen.getByText(/local engine is not connected/i)).toBeInTheDocument();
    expect(runWorkspaceCommand).not.toHaveBeenCalled();
  });

  it("asks for a git folder when no workspace is selected", async () => {
    const runWorkspaceCommand = vi.fn();
    const onOpenWorkspace = vi.fn();
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId={null}
        repositoriesClient={repos({ runWorkspaceCommand })}
        onOpenWorkspace={onOpenWorkspace}
      />,
    );

    expect(
      await screen.findByText(/open a git folder to run commands in that workspace/i),
    ).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /open folder/i }));
    expect(onOpenWorkspace).toHaveBeenCalled();
    expect(runWorkspaceCommand).not.toHaveBeenCalled();
  });

  it("runs a command in the current workspace and shows the output", async () => {
    const user = userEvent.setup();
    const runWorkspaceCommand = vi.fn(async () => ({
      command: "python probe.py",
      exitCode: 0,
      timedOut: false,
      output: "from-workspace\n",
    }));
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ runWorkspaceCommand })}
        onOpenWorkspace={() => undefined}
      />,
    );

    const input = await screen.findByRole("textbox", { name: /command/i });
    await user.type(input, "python probe.py");
    await user.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText("from-workspace")).toBeInTheDocument();
    expect(screen.getByText("Exit 0")).toBeInTheDocument();
    expect(runWorkspaceCommand).toHaveBeenCalledWith("repo_alpha", "python probe.py");
  });

  it("says so when the command times out or the engine call fails", async () => {
    const user = userEvent.setup();
    const runWorkspaceCommand = vi
      .fn()
      .mockResolvedValueOnce({
        command: "sleep 5",
        exitCode: null,
        timedOut: true,
        output: "still going",
      })
      .mockRejectedValueOnce(new Error("engine request failed: 409"));

    const { rerender } = render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ runWorkspaceCommand })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.type(await screen.findByRole("textbox", { name: /command/i }), "sleep 5");
    await user.click(screen.getByRole("button", { name: /^run$/i }));
    expect(await screen.findByText(/timed out/i)).toBeInTheDocument();
    expect(screen.getByText("still going")).toBeInTheDocument();

    rerender(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          runWorkspaceCommand: async () => {
            throw new Error("engine request failed: 409");
          },
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    const next = screen.getByRole("textbox", { name: /command/i });
    await user.clear(next);
    await user.type(next, "echo again");
    await user.click(screen.getByRole("button", { name: /^run$/i }));
    expect(
      await screen.findByText(/could not run that command. check the workspace and try again/i),
    ).toBeInTheDocument();
  });

  it("keeps Run disabled until the command box has text", async () => {
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("button", { name: /^run$/i })).toBeDisabled();
  });
});
