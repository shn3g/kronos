// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RepositoriesClient } from "../workspaces/client";
import { GoToFilePalette } from "./GoToFilePalette";

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
    listWorkspaceFiles: async () => [{ path: "src/app.py" }, { path: "README.md" }],
    readWorkspaceFile: unused,
    writeWorkspaceFile: unused,
    runWorkspaceCommand: unused,
    startWorkspaceShell: unused,
    writeWorkspaceShell: unused,
    cancelWorkspaceCommand: unused,
    watchWorkspaceCommand: unused,
    ...overrides,
  };
}

describe("GoToFilePalette", () => {
  it("does not render when closed", () => {
    render(
      <GoToFilePalette
        open={false}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onClose={() => undefined}
        onOpenWorkspace={() => undefined}
        onSelect={() => undefined}
      />,
    );

    expect(screen.queryByRole("dialog", { name: /go to file/i })).not.toBeInTheDocument();
  });

  it("asks to open a folder when no workspace is selected", async () => {
    const onOpenWorkspace = vi.fn();
    const onClose = vi.fn();
    const listWorkspaceFiles = vi.fn(async () => [{ path: "README.md" }]);
    const user = userEvent.setup();

    render(
      <GoToFilePalette
        open
        repositoryId={null}
        repositoriesClient={repos({ listWorkspaceFiles })}
        onClose={onClose}
        onOpenWorkspace={onOpenWorkspace}
        onSelect={() => undefined}
      />,
    );

    expect(screen.getByRole("dialog", { name: /go to file/i })).toBeInTheDocument();
    expect(
      screen.getByText(/open a git folder from workspaces to jump to a file/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /open folder/i }));
    expect(onOpenWorkspace).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(listWorkspaceFiles).not.toHaveBeenCalled();
  });

  it("lists files and opens the matching path", async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(
      <GoToFilePalette
        open
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onClose={onClose}
        onOpenWorkspace={() => undefined}
        onSelect={onSelect}
      />,
    );

    expect(await screen.findByRole("option", { name: "src/app.py" })).toBeInTheDocument();
    const box = screen.getByRole("combobox", { name: /go to file/i });
    await user.type(box, "app");
    expect(screen.queryByRole("option", { name: "README.md" })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("src/app.py");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("explains when the file list cannot be loaded", async () => {
    render(
      <GoToFilePalette
        open
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          listWorkspaceFiles: async () => {
            throw new Error("engine request failed: 500");
          },
        })}
        onClose={() => undefined}
        onOpenWorkspace={() => undefined}
        onSelect={() => undefined}
      />,
    );

    expect(
      await screen.findByText(
        /could not load the file list\. check that the engine is running, then try again/i,
      ),
    ).toBeInTheDocument();
  });

  it("explains when the query matches nothing", async () => {
    const user = userEvent.setup();

    render(
      <GoToFilePalette
        open
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onClose={() => undefined}
        onOpenWorkspace={() => undefined}
        onSelect={() => undefined}
      />,
    );

    await screen.findByRole("option", { name: "src/app.py" });
    await user.type(screen.getByRole("combobox", { name: /go to file/i }), "zzz");
    expect(screen.getByText(/no matching files/i)).toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("closes on Escape without choosing a file", async () => {
    const onClose = vi.fn();
    const onSelect = vi.fn();
    const user = userEvent.setup();

    render(
      <GoToFilePalette
        open
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onClose={onClose}
        onOpenWorkspace={() => undefined}
        onSelect={onSelect}
      />,
    );

    await screen.findByRole("combobox", { name: /go to file/i });
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
