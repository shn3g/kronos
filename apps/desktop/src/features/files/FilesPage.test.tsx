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
    writeWorkspaceFile: unused,
    runWorkspaceCommand: unused,
    startWorkspaceShell: unused,
    writeWorkspaceShell: unused,
    cancelWorkspaceCommand: unused,
    watchWorkspaceCommand: unused,
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

  it("lists files and opens a text file for editing", async () => {
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
    expect(await screen.findByRole("textbox", { name: "src/app.py" })).toHaveValue("print(1)\n");
    expect(screen.queryByText(/read-only/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("saves edited text into the workspace", async () => {
    const user = userEvent.setup();
    const writeWorkspaceFile = vi.fn(async () => undefined);
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ writeWorkspaceFile })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.clear(editor);
    await user.type(editor, "print(2)");
    expect(screen.getByText(/^unsaved$/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(writeWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/app.py", "print(2)");
    expect(await screen.findByRole("button", { name: /^save$/i })).toBeDisabled();
    expect(screen.queryByText(/^unsaved$/i)).not.toBeInTheDocument();
  });

  it("says so when save cannot reach the engine", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          writeWorkspaceFile: async () => {
            throw new Error("engine request failed: 500");
          },
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.type(editor, "x");
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(
      await screen.findByText(/could not save that file\. check that the engine is running, then try again/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/^unsaved$/i)).toBeInTheDocument();
  });

  it("keeps unsaved edits until save or discard when opening another file", async () => {
    const user = userEvent.setup();
    const writeWorkspaceFile = vi.fn(async () => undefined);
    const readWorkspaceFile = vi.fn(async (_id: string, path: string) => {
      if (path === "README.md") {
        return { path, content: "# hello\n", binary: false };
      }
      return { path, content: "print(1)\n", binary: false };
    });
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ readWorkspaceFile, writeWorkspaceFile })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.type(editor, "x");
    await user.click(screen.getByRole("treeitem", { name: "README.md" }));
    expect(writeWorkspaceFile).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "src/app.py" })).toHaveValue("print(1)\nx");
    expect(
      screen.getByText(/save or discard changes to src\/app\.py before opening another file/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^discard$/i }));
    expect(await screen.findByRole("textbox", { name: "README.md" })).toHaveValue("# hello\n");
  });

  it("saves from Ctrl+S while the editor is open", async () => {
    const user = userEvent.setup();
    const writeWorkspaceFile = vi.fn(async () => undefined);
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ writeWorkspaceFile })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.type(editor, "x");
    await user.keyboard("{Control>}s{/Control}");
    expect(writeWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/app.py", "print(1)\nx");
  });

  it("does not edit binary files", async () => {
    const user = userEvent.setup();
    const writeWorkspaceFile = vi.fn(async () => undefined);
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          listWorkspaceFiles: async () => [{ path: "logo.png" }],
          readWorkspaceFile: async () => ({ path: "logo.png", content: "", binary: true }),
          writeWorkspaceFile,
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "logo.png" }));
    expect(
      await screen.findByText(/this file is binary, so kronos is not showing its contents/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "logo.png" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    expect(writeWorkspaceFile).not.toHaveBeenCalled();
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

  it("asks in chat for the selected file", async () => {
    const user = userEvent.setup();
    const onAskInChat = vi.fn();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
        onAskInChat={onAskInChat}
      />,
    );

    expect(screen.queryByRole("button", { name: /ask in chat/i })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    await user.click(await screen.findByRole("button", { name: /ask in chat/i }));
    expect(onAskInChat).toHaveBeenCalledWith("src/app.py");
  });

  it("searches workspace contents and opens a hit in the preview", async () => {
    const user = userEvent.setup();
    const search = vi.fn(async () => [
      {
        path: "src/app.py",
        startLine: 1,
        endLine: 4,
        commit: "abc123",
        symbol: "connect",
        rankSources: ["sparse"],
        trust: "tracked",
        text: "def connect",
      },
    ]);
    const readWorkspaceFile = vi.fn(async (_id: string, path: string) => ({
      path,
      content: "print(1)\n",
      binary: false,
    }));
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ readWorkspaceFile })}
        indexClient={{
          status: async () => ({
            repositoryId: "repo_alpha",
            commit: "abc123",
            chunkCount: 4,
            denseAvailable: false,
            indexPath: "C:/cache/indexes/repo_alpha",
            ready: true,
          }),
          rebuild: async () => {
            throw new Error("rebuild should not run");
          },
          search,
        }}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.type(await screen.findByRole("searchbox", { name: /search contents/i }), "connect");
    await user.click(screen.getByRole("button", { name: /^search$/i }));
    expect(search).toHaveBeenCalledWith("repo_alpha", "connect");
    await user.click(await screen.findByRole("button", { name: "src/app.py" }));
    expect(readWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/app.py");
    expect(await screen.findByRole("textbox", { name: "src/app.py" })).toHaveValue("print(1)\n");
  });

  it("shows a specific error when content search fails", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        indexClient={{
          status: async () => ({
            repositoryId: "repo_alpha",
            commit: "abc123",
            chunkCount: 4,
            denseAvailable: false,
            indexPath: "C:/cache/indexes/repo_alpha",
            ready: true,
          }),
          rebuild: async () => {
            throw new Error("rebuild should not run");
          },
          search: async () => {
            throw new Error("engine request failed: 500");
          },
        }}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.type(await screen.findByRole("searchbox", { name: /search contents/i }), "connect");
    await user.click(screen.getByRole("button", { name: /^search$/i }));
    expect(
      await screen.findByText(
        /could not search this workspace\. check that the engine is running, then try again/i,
      ),
    ).toBeInTheDocument();
  });

  it("reveals a nested file from an external request without a tree click", async () => {
    const readWorkspaceFile = vi.fn(async (_id: string, path: string) => ({
      path,
      content: "print(1)\n",
      binary: false,
    }));

    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ readWorkspaceFile })}
        onOpenWorkspace={() => undefined}
        revealRequest={{ path: "src/app.py", nonce: 1 }}
      />,
    );

    expect(await screen.findByRole("textbox", { name: "src/app.py" })).toHaveValue("print(1)\n");
    expect(readWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/app.py");
    expect(screen.getByRole("treeitem", { name: "app.py" })).toHaveAttribute("aria-selected", "true");
  });

  it("ignores an empty reveal request", async () => {
    const readWorkspaceFile = vi.fn(async () => ({
      path: "src/app.py",
      content: "print(1)\n",
      binary: false,
    }));

    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ readWorkspaceFile })}
        onOpenWorkspace={() => undefined}
        revealRequest={{ path: "", nonce: 0 }}
      />,
    );

    expect(await screen.findByRole("treeitem", { name: "src" })).toBeInTheDocument();
    expect(screen.getByText(/select a file to open it/i)).toBeInTheDocument();
    expect(readWorkspaceFile).not.toHaveBeenCalled();
  });

  it("ignores a parent-directory reveal path", async () => {
    const readWorkspaceFile = vi.fn(async () => ({
      path: "secret.txt",
      content: "nope\n",
      binary: false,
    }));

    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ readWorkspaceFile })}
        onOpenWorkspace={() => undefined}
        revealRequest={{ path: "../secret.txt", nonce: 1 }}
      />,
    );

    expect(await screen.findByRole("treeitem", { name: "src" })).toBeInTheDocument();
    expect(screen.getByText(/select a file to open it/i)).toBeInTheDocument();
    expect(readWorkspaceFile).not.toHaveBeenCalled();
  });
});
