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
    get: unused,
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
    writeFile: unused,
    writeWorkspaceFile: unused,
    runWorkspaceCommand: unused,
    startWorkspaceShell: async () => ({
      command: "shell",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: "",
    }),
    writeWorkspaceShell: async () => ({ ok: true }),
    resizeWorkspaceShell: async () => ({ ok: true }),
    cancelWorkspaceCommand: unused,
    watchWorkspaceCommand: async () => ({
      command: "shell",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: "",
    }),
    ...overrides,
  };
}

describe("TerminalPage", () => {
  it("stays closed when the engine is not ready", async () => {
    const startWorkspaceShell = vi.fn();
    render(
      <TerminalPage
        engineClient={engine("unavailable")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ startWorkspaceShell })}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("heading", { level: 2, name: "Terminal" })).toBeInTheDocument();
    expect(screen.getByText(/local engine is not connected/i)).toBeInTheDocument();
    expect(startWorkspaceShell).not.toHaveBeenCalled();
  });

  it("asks for a git folder when no workspace is selected", async () => {
    const startWorkspaceShell = vi.fn();
    const onOpenWorkspace = vi.fn();
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId={null}
        repositoriesClient={repos({ startWorkspaceShell })}
        onOpenWorkspace={onOpenWorkspace}
      />,
    );

    expect(
      await screen.findByText(/open a workspace to run commands here/i),
    ).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /open folder/i }));
    expect(onOpenWorkspace).toHaveBeenCalled();
    expect(startWorkspaceShell).not.toHaveBeenCalled();
  });

  it("sends keystrokes to the live shell and keeps the prompt open", async () => {
    const user = userEvent.setup();
    const writes: string[] = [];
    let live = "";
    const writeWorkspaceShell = vi.fn(async (_id: string, data: string) => {
      writes.push(data);
      live += data;
      return { ok: true };
    });
    const watchWorkspaceCommand = vi.fn(async () => ({
      command: "shell",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: live,
    }));
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ writeWorkspaceShell, watchWorkspaceCommand })}
        onOpenWorkspace={() => undefined}
      />,
    );

    const terminal = await screen.findByRole("textbox", { name: /^terminal$/i });
    await user.type(terminal, "echo hello-shell{Enter}");

    expect(writes.join("")).toBe("echo hello-shell\r");
    expect(writeWorkspaceShell).toHaveBeenCalledWith("repo_alpha", "e");
    expect(await screen.findByText(/hello-shell/)).toBeInTheDocument();
    expect(screen.getByText("Shell is open.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^send$/i })).not.toBeInTheDocument();
  });

  it("keeps earlier output when more keys are sent", async () => {
    const user = userEvent.setup();
    let live = "";
    const writeWorkspaceShell = vi.fn(async (_id: string, data: string) => {
      live += data;
      return { ok: true };
    });
    const watchWorkspaceCommand = vi.fn(async () => ({
      command: "shell",
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: live,
    }));
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ writeWorkspaceShell, watchWorkspaceCommand })}
        onOpenWorkspace={() => undefined}
      />,
    );

    const terminal = await screen.findByRole("textbox", { name: /^terminal$/i });
    await user.type(terminal, "echo hello-shell{Enter}");
    expect(await screen.findByText(/hello-shell/)).toBeInTheDocument();
    await user.type(terminal, "echo second-line{Enter}");
    expect(await screen.findByText(/second-line/)).toBeInTheDocument();
    expect(screen.getByText(/hello-shell/)).toBeInTheDocument();
  });

  it("stops the shell without waiting for a command timeout", async () => {
    const user = userEvent.setup();
    let running = true;
    const cancelWorkspaceCommand = vi.fn(async () => {
      running = false;
      return { ok: true };
    });
    const watchWorkspaceCommand = vi.fn(async () => ({
      command: "shell",
      exitCode: null,
      timedOut: false,
      cancelled: !running,
      running,
      output: "",
    }));
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ cancelWorkspaceCommand, watchWorkspaceCommand })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await screen.findByText("Shell is open.");
    await user.click(await screen.findByRole("button", { name: /^stop$/i }));
    expect(cancelWorkspaceCommand).toHaveBeenCalledWith("repo_alpha");
    expect(await screen.findByText("Stopped.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^stop$/i })).not.toBeInTheDocument();
  });

  it("says so when stop cannot reach the engine", async () => {
    const user = userEvent.setup();
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          cancelWorkspaceCommand: async () => {
            throw new Error("engine request failed: 500");
          },
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await screen.findByText("Shell is open.");
    await user.click(await screen.findByRole("button", { name: /^stop$/i }));
    expect(
      await screen.findByText(/could not stop that command. wait for it to finish, then try again/i),
    ).toBeInTheDocument();
  });

  it("says so when the shell cannot start or a line cannot be sent", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          startWorkspaceShell: async () => {
            throw new Error("engine request failed: 500");
          },
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(
      await screen.findByText(
        /could not start the workspace shell. check that the engine is running, then try again/i,
      ),
    ).toBeInTheDocument();

    rerender(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          writeWorkspaceShell: async () => {
            throw new Error("engine request failed: 409");
          },
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    const next = await screen.findByRole("textbox", { name: /^terminal$/i });
    await user.type(next, "echo again{Enter}");
    expect(
      await screen.findByText(/could not send that key. check that the engine is running, then try again/i),
    ).toBeInTheDocument();
  });

  it("keeps the terminal ready for typing while the shell is open", async () => {
    render(
      <TerminalPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("textbox", { name: /^terminal$/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /^send$/i })).not.toBeInTheDocument();
  });
});
