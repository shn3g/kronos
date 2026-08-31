// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { IndexPage, type IndexPageClients } from "./IndexPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
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
    status: async () => ({
      repositoryId: "repo_alpha",
      commit: "abc123",
      chunkCount: 4,
      denseAvailable: false,
      indexPath: "C:/cache/indexes/repo_alpha",
      ready: true,
    }),
    rebuild: async () => ({
      repositoryId: "repo_alpha",
      commit: "abc123",
      chunkCount: 4,
      denseAvailable: false,
      indexPath: "C:/cache/indexes/repo_alpha",
      ready: true,
    }),
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
      screen.getByText(/connect a compatible engine to inspect repository indexes/i),
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
    await user.type(screen.getByRole("searchbox", { name: /search index/i }), "connect");
    await user.click(screen.getByRole("button", { name: /search/i }));
    expect(search).toHaveBeenCalledWith("repo_alpha", "connect");
    expect(await screen.findByText("pkg/db.py")).toBeInTheDocument();
    expect(screen.getByText(/sparse, graph/i)).toBeInTheDocument();
  });
});
