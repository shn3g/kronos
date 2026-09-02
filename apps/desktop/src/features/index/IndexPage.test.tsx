// SPDX-License-Identifier: AGPL-3.0-or-later

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { IndexPage, type IndexPageClients } from "./IndexPage";
import type { IndexStatus } from "./client";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function status(overrides: Partial<IndexStatus> = {}): IndexStatus {
  return {
    repositoryId: "repo_alpha",
    commit: "abc123",
    chunkCount: 4,
    denseAvailable: false,
    indexPath: "C:/cache/indexes/repo_alpha",
    ready: true,
    state: "idle",
    filesDone: 4,
    filesTotal: 4,
    chunksEmbedded: 3,
    chunksSkipped: 1,
    lastActivityAt: "2026-09-01T15:00:00+00:00",
    watchEnabled: true,
    ...overrides,
  };
}

function clients(overrides: Partial<IndexPageClients> = {}): IndexPageClients {
  return {
    listRepositories: async () => [
      {
        id: "repo_alpha",
        displayName: "alpha",
        realpath: "C:/tmp/alpha",
        origin: "https://github.com/acme/alpha.git",
        status: "active",
      },
    ],
    status: async () => status(),
    rebuild: async () => status(),
    setWatch: async () => status({ watchEnabled: false }),
    search: async () => [
      {
        path: "pkg/db.py",
        startLine: 1,
        endLine: 4,
        commit: "abc123",
        symbol: "connect",
        rankSources: ["sparse", "graph"],
        trust: "tracked",
        text: "def connect",
      },
    ],
    ...overrides,
  };
}

describe("IndexPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const status = vi.fn(async () => clients().status("repo_alpha"));
    render(<IndexPage engineClient={engine("unavailable")} indexClient={clients({ status })} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Index" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /rebuild index/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(status).not.toHaveBeenCalled();
  });

  it("shows index status and search hits when the engine is ready", async () => {
    const user = userEvent.setup();
    const search = vi.fn(async () => [
      {
        path: "pkg/db.py",
        startLine: 1,
        endLine: 4,
        commit: "abc123",
        symbol: "connect",
        rankSources: ["sparse", "graph"],
        trust: "tracked",
        text: "def connect",
      },
    ]);
    render(<IndexPage engineClient={engine("ready")} indexClient={clients({ search })} />);

    expect(await screen.findByText(/chunk count/i)).toBeInTheDocument();
    expect(screen.getByText(/dense unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/^idle$/i)).toBeInTheDocument();
    expect(screen.getByText("4 / 4")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByLabelText(/watch working tree/i)).toBeChecked();
    await user.type(screen.getByRole("searchbox", { name: /search index/i }), "connect");
    await user.click(screen.getByRole("button", { name: /search/i }));
    expect(search).toHaveBeenCalledWith("repo_alpha", "connect");
    expect(await screen.findByText("pkg/db.py")).toBeInTheDocument();
    expect(screen.getByText(/sparse, graph/i)).toBeInTheDocument();
  });

  it("clears previous status when switching repositories and ignores stale responses", async () => {
    const user = userEvent.setup();
    const bravoWaiters: Array<(value: IndexStatus) => void> = [];
    const statusFn = vi.fn(async (id: string) => {
      if (id === "repo_bravo") {
        return await new Promise<IndexStatus>((resolve) => {
          bravoWaiters.push(resolve);
        });
      }
      return status({
        repositoryId: "repo_alpha",
        commit: "alpha-commit",
        watchEnabled: true,
      });
    });
    let finishWatch: (value: IndexStatus) => void = () => {};
    const setWatch = vi.fn(
      async () =>
        await new Promise<IndexStatus>((resolve) => {
          finishWatch = resolve;
        }),
    );
    render(
      <IndexPage
        engineClient={engine("ready")}
        indexClient={clients({
          listRepositories: async () => [
            {
              id: "repo_alpha",
              displayName: "alpha",
              realpath: "C:/tmp/alpha",
              origin: "https://github.com/acme/alpha.git",
              status: "active",
            },
            {
              id: "repo_bravo",
              displayName: "bravo",
              realpath: "C:/tmp/bravo",
              origin: "https://github.com/acme/bravo.git",
              status: "active",
            },
          ],
          status: statusFn,
          setWatch,
        })}
      />,
    );

    expect(await screen.findByText("alpha-commit")).toBeInTheDocument();
    await user.click(screen.getByLabelText(/watch working tree/i));
    await user.selectOptions(screen.getByRole("combobox", { name: /repository/i }), "repo_bravo");
    expect(screen.queryByText("alpha-commit")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/watch working tree/i)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: /repository/i }), "repo_alpha");
    expect(await screen.findByText("alpha-commit")).toBeInTheDocument();
    const bravoStatus = status({
      repositoryId: "repo_bravo",
      commit: "stale-bravo",
      watchEnabled: false,
      chunkCount: 99,
    });
    await act(async () => {
      for (const resolve of bravoWaiters) {
        resolve(bravoStatus);
      }
      finishWatch(
        status({
          repositoryId: "repo_alpha",
          commit: "stale-watch",
          watchEnabled: false,
          chunkCount: 99,
        }),
      );
      await Promise.resolve();
    });
    expect(screen.queryByText("stale-bravo")).not.toBeInTheDocument();
    expect(screen.queryByText("stale-watch")).not.toBeInTheDocument();
    expect(screen.getByText("alpha-commit")).toBeInTheDocument();
    expect(screen.getByLabelText(/watch working tree/i)).toBeChecked();
  });

  it("ignores delayed search hits after switching repositories", async () => {
    const user = userEvent.setup();
    const alphaHits = [
      {
        path: "alpha-only.py",
        startLine: 1,
        endLine: 2,
        commit: "alpha-commit",
        symbol: "alpha_fn",
        rankSources: ["sparse"],
        trust: "tracked",
        text: "def alpha_fn",
      },
    ];
    let finishAlphaSearch: (value: typeof alphaHits) => void = () => {};
    const search = vi.fn(async (id: string) => {
      if (id === "repo_alpha") {
        return await new Promise<typeof alphaHits>((resolve) => {
          finishAlphaSearch = resolve;
        });
      }
      return [];
    });
    render(
      <IndexPage
        engineClient={engine("ready")}
        indexClient={clients({
          listRepositories: async () => [
            {
              id: "repo_alpha",
              displayName: "alpha",
              realpath: "C:/tmp/alpha",
              origin: "https://github.com/acme/alpha.git",
              status: "active",
            },
            {
              id: "repo_bravo",
              displayName: "bravo",
              realpath: "C:/tmp/bravo",
              origin: "https://github.com/acme/bravo.git",
              status: "active",
            },
          ],
          search,
        })}
      />,
    );

    expect(await screen.findByRole("searchbox", { name: /search index/i })).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: /search index/i }), "alpha");
    await user.click(screen.getByRole("button", { name: /search/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /repository/i }), "repo_bravo");
    expect(screen.queryByText("alpha-only.py")).not.toBeInTheDocument();

    await act(async () => {
      finishAlphaSearch(alphaHits);
      await Promise.resolve();
    });
    expect(screen.queryByText("alpha-only.py")).not.toBeInTheDocument();
    expect(search).toHaveBeenCalledWith("repo_alpha", "alpha");
  });

  it("shows the dense backend name when dense is available", async () => {
    render(
      <IndexPage
        engineClient={engine("ready")}
        indexClient={clients({
          status: async () => status({ denseAvailable: true }),
        })}
        modelsClient={{
          snapshot: async () => ({
            detected: [],
            profiles: [],
            assignments: {
              orchestrator: null,
              planner: null,
              coder: null,
              reviewer: null,
              embedding: null,
            },
            embeddingBackend: {
              kind: "onnx",
              modelId: "BAAI/bge-small-en-v1.5",
              displayName: "bge-small-en-v1.5",
            },
          }),
        }}
      />,
    );
    expect(await screen.findByText(/bge-small-en-v1.5 \(ready\)/i)).toBeInTheDocument();
  });

  it("toggles the watcher without rebuilding", async () => {
    const user = userEvent.setup();
    const setWatch = vi.fn(async (_id: string, enabled: boolean) =>
      status({ watchEnabled: enabled }),
    );
    render(
      <IndexPage engineClient={engine("ready")} indexClient={clients({ setWatch })} />,
    );
    const toggle = await screen.findByLabelText(/watch working tree/i);
    await user.click(toggle);
    expect(setWatch).toHaveBeenCalledWith("repo_alpha", false);
  });
});
