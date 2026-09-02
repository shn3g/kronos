// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EmbeddingBackend, ModelsClient, RoleAssignments } from "../features/models/client";
import { embeddingInstallClientStubs } from "../features/models/client";
import { ConnectModelGate } from "./ConnectModelGate";

const EMPTY_BACKEND: EmbeddingBackend = {
  kind: "none",
  modelId: "",
  displayName: "Sparse only",
};

function emptyAssignments(): RoleAssignments {
  return {
    orchestrator: null,
    planner: null,
    coder: null,
    reviewer: null,
    embedding: null,
  };
}

function filledAssignments(id: string): RoleAssignments {
  return {
    orchestrator: id,
    planner: id,
    coder: id,
    reviewer: id,
    embedding: id,
  };
}

function plannerProfile(id: string) {
  return {
    id,
    displayName: "Local (planner)",
    role: "planner",
    billed: false,
    modelId: "llama3",
    limits: { maxTokens: 0, maxAttempts: 0, timeoutSeconds: 0, costCeiling: 0, contextWindow: 32000 },
  };
}

function modelsClient(overrides: Partial<ModelsClient> = {}): ModelsClient {
  return {
    ...embeddingInstallClientStubs,
    snapshot: async () => ({
      detected: [],
      profiles: [],
      assignments: emptyAssignments(),
      embeddingBackend: EMPTY_BACKEND,
    }),
    assign: async () => filledAssignments("prof_1"),
    createProvider: async () => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "Local",
        billed: false,
      },
      profiles: [plannerProfile("prof_1")],
    }),
    updateProfile: async (id) => plannerProfile(id),
    ...overrides,
  };
}

describe("ConnectModelGate", () => {
  it("offers one-click use of a detected local OpenAI server", async () => {
    const user = userEvent.setup();
    const createProvider = vi.fn(async (draft: { baseUrl: string | null }) => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: draft.baseUrl ?? "Local",
        billed: false,
      },
      profiles: [plannerProfile("prof_1")],
    }));
    const assign = vi.fn(async () => filledAssignments("prof_1"));
    const onConnected = vi.fn();
    render(
      <ConnectModelGate
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [
              { kind: "openai_compatible", label: "http://127.0.0.1:11434/v1", present: true },
            ],
            profiles: [],
            assignments: emptyAssignments(),
            embeddingBackend: EMPTY_BACKEND,
          }),
          createProvider,
          assign,
        })}
        onConnected={onConnected}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /use http:\/\/127\.0\.0\.1:11434\/v1/i }));
    expect(createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "openai_compatible",
        baseUrl: "http://127.0.0.1:11434/v1",
        billed: false,
      }),
    );
    expect(assign).toHaveBeenCalledWith(
      {
        orchestrator: "prof_1",
        planner: "prof_1",
        coder: "prof_1",
        reviewer: "prof_1",
        embedding: "prof_1",
      },
      { confirmSharedRoles: true },
    );
    expect(onConnected).toHaveBeenCalled();
  });

  it("fills a hosted OpenAI URL from a preset and requires a key", async () => {
    const user = userEvent.setup();
    const createProvider = vi.fn(async (draft: { baseUrl: string | null; billed: boolean }) => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "OpenAI",
        billed: draft.billed,
      },
      profiles: [plannerProfile("prof_1")],
    }));
    const assign = vi.fn(async () => filledAssignments("prof_1"));
    render(
      <ConnectModelGate
        modelsClient={modelsClient({ createProvider, assign })}
        onConnected={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: /^openrouter$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /opencode zen/i })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /^openai$/i }));
    expect(screen.getByRole("button", { name: /^openai$/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText(/^name$/i)).toHaveValue("OpenAI");
    expect(screen.getByLabelText(/api url/i)).toHaveValue("https://api.openai.com/v1");
    expect(screen.getByLabelText(/model id/i)).toHaveValue("gpt-4o-mini");
    await user.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(createProvider).not.toHaveBeenCalled();
    expect(screen.getByText(/hosted api needs a key/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^api key$/i), "sk-test");
    await user.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        billed: false,
        baseUrl: "https://api.openai.com/v1",
        apiKey: "sk-test",
        modelId: "gpt-4o-mini",
      }),
    );
    expect(assign).toHaveBeenCalled();
  });

  it("says Cursor CLI cannot chat until a model API is connected", async () => {
    render(
      <ConnectModelGate
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [{ kind: "cursor_cli", label: "cursor-agent", present: true }],
            profiles: [],
            assignments: emptyAssignments(),
            embeddingBackend: EMPTY_BACKEND,
          }),
        })}
        onConnected={() => undefined}
      />,
    );

    expect(
      await screen.findByText(/cursor cli is on this machine/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/chat still needs a model api/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /use http/i })).not.toBeInTheDocument();
  });
});
