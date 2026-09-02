// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DESKTOP_CLIENT_VERSION } from "../../api/kronosClient";
import type { EngineClient } from "../../engine/client";
import type { IndexClient } from "../index/client";
import type { RepositoriesClient } from "../workspaces/client";
import { FilesPage } from "./FilesPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: DESKTOP_CLIENT_VERSION }) };
  }
  return { getState: async () => ({ status }) };
}

function unused(): Promise<never> {
  return Promise.reject(new Error("unused"));
}

function idleIndex(search: IndexClient["search"]): IndexClient {
  const status = {
    repositoryId: "repo_alpha",
    commit: "abc123",
    chunkCount: 4,
    denseAvailable: false,
    indexPath: "C:/cache/indexes/repo_alpha",
    ready: true,
    state: "idle" as const,
    filesDone: 0,
    filesTotal: 0,
    chunksEmbedded: 0,
    chunksSkipped: 0,
    lastActivityAt: null,
    watchEnabled: false,
  };
  return {
    status: async () => status,
    rebuild: async () => status,
    setWatch: async () => status,
    search,
  };
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
    listChanges: async () => [],
    writeFile: unused,
    listWorkspaceFiles: async () => [{ path: "src/app.py" }, { path: "README.md" }],
    readWorkspaceFile: async () => ({ path: "src/app.py", content: "print(1)\n", binary: false }),
    writeWorkspaceFile: unused,
    revertWrite: unused,
    commitFiles: unused,
    runWorkspaceCommand: unused,
    startWorkspaceShell: unused,
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
    expect(screen.getByText(/files load after the engine connects/i)).toBeInTheDocument();
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

  it("indents selected lines with Tab and outdents with Shift+Tab", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "alpha\nbeta\ngamma\n",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = (await screen.findByRole("textbox", { name: "src/app.py" })) as HTMLTextAreaElement;
    editor.focus();
    editor.setSelectionRange(0, 10);
    await user.keyboard("{Tab}");
    expect(editor).toHaveValue("  alpha\n  beta\ngamma\n");
    await waitFor(() => {
      expect(editor).toHaveProperty("selectionStart", 0);
      expect(editor).toHaveProperty("selectionEnd", 14);
    });
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(editor).toHaveValue("alpha\nbeta\ngamma\n");
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
    expect(onAskInChat).toHaveBeenCalledWith("src/app.py", null);
  });

  it("asks in chat with the selected editor lines", async () => {
    const user = userEvent.setup();
    const onAskInChat = vi.fn();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "alpha\nbeta\ngamma\n",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
        onAskInChat={onAskInChat}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = (await screen.findByRole("textbox", { name: "src/app.py" })) as HTMLTextAreaElement;
    editor.focus();
    editor.setSelectionRange(6, 10);
    await user.click(screen.getByRole("button", { name: /ask in chat/i }));
    expect(onAskInChat).toHaveBeenCalledWith("src/app.py", {
      text: "beta",
      startLine: 2,
      endLine: 2,
    });
  });

  it("asks in chat from the Ask in chat event with the current selection", async () => {
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

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = (await screen.findByRole("textbox", { name: "src/app.py" })) as HTMLTextAreaElement;
    editor.focus();
    editor.setSelectionRange(0, 8);
    window.dispatchEvent(new Event("kronos-ask-in-chat"));
    expect(onAskInChat).toHaveBeenCalledWith("src/app.py", {
      text: "print(1)",
      startLine: 1,
      endLine: 1,
    });
  });

  it("searches workspace contents and opens a hit in the preview", async () => {
    const user = userEvent.setup();
    const search = vi.fn(async () => [
      {
        path: "src/app.py",
        startLine: 2,
        endLine: 4,
        commit: "abc123",
        symbol: "connect",
        rankSources: ["sparse"],
        trust: "tracked",
        text: "def connect():\n    pass",
      },
    ]);
    const readWorkspaceFile = vi.fn(async (_id: string, path: string) => ({
      path,
      content: "print(0)\ndef connect():\n    pass\n",
      binary: false,
    }));
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({ readWorkspaceFile })}
        indexClient={idleIndex(search)}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.type(await screen.findByRole("searchbox", { name: /search contents/i }), "connect");
    await user.click(screen.getByRole("button", { name: /^search$/i }));
    expect(search).toHaveBeenCalledWith("repo_alpha", "connect");
    const hit = await screen.findByRole("button", { name: /src\/app\.py:2/i });
    expect(hit).toHaveTextContent("def connect(): pass");
    await user.click(hit);
    expect(readWorkspaceFile).toHaveBeenCalledWith("repo_alpha", "src/app.py");
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    expect(editor).toHaveValue("print(0)\ndef connect():\n    pass\n");
    expect(editor).toHaveProperty("selectionStart", 9);
    expect(editor).toHaveProperty("selectionEnd", 23);
  });

  it("focuses workspace search when Find in files is requested", async () => {
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        indexClient={idleIndex(async () => [])}
        onOpenWorkspace={() => undefined}
      />,
    );

    await screen.findByRole("searchbox", { name: /search contents/i });
    window.dispatchEvent(new Event("kronos-find-in-files"));
    await waitFor(() => {
      expect(screen.getByRole("searchbox", { name: /search contents/i })).toHaveFocus();
    });
  });

  it("shows a specific error when content search fails", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        indexClient={idleIndex(async () => {
          throw new Error("engine request failed: 500");
        })}
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

  it("shows a line-number gutter for the open file", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    await screen.findByRole("textbox", { name: "src/app.py" });
    const lines = [...document.querySelectorAll(".files-page__gutter li")].map((node) => node.textContent);
    expect(lines).toEqual(["1", "2"]);
  });

  it("finds matches in the open file and steps through them", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "alpha\nbeta\nalpha\n",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.keyboard("{Control>}f{/Control}");
    const find = await screen.findByRole("searchbox", { name: /find in file/i });
    await user.type(find, "alpha");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    expect(editor).toHaveProperty("selectionStart", 0);
    expect(editor).toHaveProperty("selectionEnd", 5);
    await user.click(screen.getByRole("button", { name: /^next$/i }));
    expect(screen.getByText("2 of 2")).toBeInTheDocument();
    expect(editor).toHaveProperty("selectionStart", 11);
    expect(editor).toHaveProperty("selectionEnd", 16);
    await user.click(screen.getByRole("button", { name: /^previous$/i }));
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
  });

  it("says so when find matches nothing, and Escape closes the bar", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    await screen.findByRole("textbox", { name: "src/app.py" });
    await user.keyboard("{Control>}f{/Control}");
    await user.type(await screen.findByRole("searchbox", { name: /find in file/i }), "zzz");
    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("searchbox", { name: /find in file/i })).not.toBeInTheDocument();
  });

  it("colors Python keywords in the open file", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "def foo():\n    return 1\n",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    expect(await screen.findByRole("textbox", { name: "src/app.py" })).toHaveValue(
      "def foo():\n    return 1\n",
    );
    const keywords = [...document.querySelectorAll(".files-page__hl--keyword")].map(
      (node) => node.textContent,
    );
    expect(keywords).toEqual(["def", "return"]);
    expect(document.querySelector(".files-page__hl--number")).toHaveTextContent("1");
  });

  it("replaces the current match and can replace all remaining matches", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "alpha\nbeta\nalpha\n",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.keyboard("{Control>}h{/Control}");
    await user.type(await screen.findByRole("searchbox", { name: /find in file/i }), "alpha");
    await user.type(screen.getByRole("textbox", { name: /replace with/i }), "one");
    await user.click(screen.getByRole("button", { name: /^replace$/i }));
    expect(editor).toHaveValue("one\nbeta\nalpha\n");
    expect(screen.getByText("1 of 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^replace all$/i }));
    expect(editor).toHaveValue("one\nbeta\none\n");
    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  });

  it("jumps to a line in the open file", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "alpha\nbeta\ngamma\n",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.keyboard("{Control>}g{/Control}");
    await user.type(await screen.findByRole("textbox", { name: /go to line/i }), "2");
    await user.keyboard("{Enter}");
    expect(editor).toHaveProperty("selectionStart", 6);
    expect(editor).toHaveProperty("selectionEnd", 10);
    expect(screen.getByText("Line 2 of 4")).toBeInTheDocument();
  });

  it("can require the same letter case when finding in the open file", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "Alpha\nalpha\n",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.keyboard("{Control>}f{/Control}");
    await user.type(await screen.findByRole("searchbox", { name: /find in file/i }), "alpha");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /match case/i }));
    expect(screen.getByText("1 of 1")).toBeInTheDocument();
    expect(editor).toHaveProperty("selectionStart", 6);
    expect(editor).toHaveProperty("selectionEnd", 11);
  });

  it("can require a whole word when finding in the open file", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos({
          readWorkspaceFile: async () => ({
            path: "src/app.py",
            content: "cat catalog cat",
            binary: false,
          }),
        })}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    const editor = await screen.findByRole("textbox", { name: "src/app.py" });
    await user.keyboard("{Control>}f{/Control}");
    await user.type(await screen.findByRole("searchbox", { name: /find in file/i }), "cat");
    expect(screen.getByText("1 of 3")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /whole word/i }));
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    expect(editor).toHaveProperty("selectionStart", 0);
    expect(editor).toHaveProperty("selectionEnd", 3);
    await user.click(screen.getByRole("button", { name: /^next$/i }));
    expect(editor).toHaveProperty("selectionStart", 12);
    expect(editor).toHaveProperty("selectionEnd", 15);
  });

  it("says so when a find regular expression is not valid", async () => {
    const user = userEvent.setup();
    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("treeitem", { name: "src" }));
    await user.click(screen.getByRole("treeitem", { name: "app.py" }));
    await screen.findByRole("textbox", { name: "src/app.py" });
    await user.keyboard("{Control>}f{/Control}");
    await user.click(screen.getByRole("checkbox", { name: /regular expression/i }));
    await user.type(await screen.findByRole("searchbox", { name: /find in file/i }), "[[");
    expect(screen.getByText(/that regular expression is not valid/i)).toBeInTheDocument();
  });

  it("indents nested file-tree rows with --tree-depth, matching the CSS variable", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const css = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../../styles/shell.css"),
      "utf8",
    );
    const itemRule = css.match(/\.files-page__item \{[^}]+\}/)?.[0] ?? "";

    render(
      <FilesPage
        engineClient={engine("ready")}
        repositoryId="repo_alpha"
        repositoriesClient={repos()}
        onOpenWorkspace={() => undefined}
      />,
    );
    await userEvent.setup().click(await screen.findByRole("treeitem", { name: "src" }));
    const nested = screen.getByRole("treeitem", { name: "app.py" });

    expect(nested.style.getPropertyValue("--tree-depth")).toBe("1");
    expect(itemRule).toContain("var(--tree-depth");
    expect(itemRule).not.toContain("var(--depth");
  });
});
