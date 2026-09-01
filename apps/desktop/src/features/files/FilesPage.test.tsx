// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import type { RepositoriesClient } from "../workspaces/client";
import { FilesPage } from "./FilesPage";

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
    listWorkspaceFiles: async () => [{ path: "src/app.py" }, { path: "README.md" }],
    readWorkspaceFile: async () => ({ path: "src/app.py", content: "print(1)\n", binary: false }),
    ...overrides,
  };
}

describe("FilesPage", () => {
  it("stays closed when the engine is not ready", async () => {
    const listWorkspaceFiles = vi.fn(async () => [{ path: "README.md" }]);
    render(
      <FilesPage
        engineClient={engine("unavailable")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ listWorkspaceFiles })}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Files" })).toBeInTheDocument();
    expect(screen.getByText(/connect a compatible engine to browse workspace files/i)).toBeInTheDocument();
    expect(screen.queryByRole("tree", { name: /workspace files/i })).not.toBeInTheDocument();
    expect(listWorkspaceFiles).not.toHaveBeenCalled();
  });

  it("asks to open a folder when no workspace is selected", async () => {
    const onOpenWorkspace = vi.fn();
    const listWorkspaceFiles = vi.fn(async () => [{ path: "README.md" }]);
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId={null}
        repositoriesClient={repos({ listWorkspaceFiles })}
        onOpenWorkspace={onOpenWorkspace}
      />,
    );

    expect(await screen.findByText(/open a git folder from workspaces to browse files here/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /open folder/i }));
    expect(onOpenWorkspace).toHaveBeenCalledTimes(1);
    expect(listWorkspaceFiles).not.toHaveBeenCalled();
  });

  it("lists files and shows a read-only preview", async () => {
    const user = userEvent.setup();
    const readWorkspaceFile = vi.fn(async (id: string, path: string) => {
      expect(id).toBe("repo_alpha");
      if (path === "src/app.py") {
        return { path, content: "print(1)\n", binary: false };
      }
      return { path, content: "# hello\n", binary: false };
    });
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ readWorkspaceFile })}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(await screen.findByRole("treeitem", { name: "README.md" })).toBeInTheDocument();
    await user.click(screen.getByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    expect(await screen.findByText("print(1)")).toBeInTheDocument();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
  });

  it("shows a specific error when listing fails", async () => {
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          listWorkspaceFiles: async () => {
            throw new Error("engine request failed: 500");
          },
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    expect(
      await screen.findByText(/could not load the file list\. check that the engine is running, then try again/i),
    ).toBeInTheDocument();
  });

  it("filters the tree by file name", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.type(await screen.findByRole("searchbox", { name: /filter files/i }), "readme");
    expect(await screen.findByRole("treeitem", { name: "README.md" })).toBeInTheDocument();
    expect(screen.queryByRole("treeitem", { name: "src" })).not.toBeInTheDocument();
  });
});
