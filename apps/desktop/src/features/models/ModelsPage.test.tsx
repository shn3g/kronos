// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { ModelsPage, type ModelsClient } from "./ModelsPage";
import type { ModelRole } from "./client";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function modelsClient(overrides: Partial<ModelsClient> = {}): ModelsClient {
  return {
    snapshot: async () => ({
      detected: [
        { kind: "cursor_cli", label: "cursor-agent", present: true },
        {
          kind: "openai_compatible",
          label: "http://127.0.0.1:11434/v1",
          present: true,
        },
      ],
      profiles: [
        { id: "prof_local", displayName: "Local llama3", role: "coder", billed: false },
        { id: "prof_embed", displayName: "Local embed", role: "embedding", billed: false },
      ],
      assignments: {
        planner: "prof_local",
        coder: "prof_local",
        reviewer: "prof_local",
        embedding: "prof_embed",
      },
      embeddingBackend: {
        kind: "onnx",
        modelId: "all-MiniLM-L6-v2",
        displayName: "Local ONNX",
      },
    }),
    assign: async () => ({
      planner: "prof_local",
      coder: "prof_local",
      reviewer: "prof_local",
      embedding: "prof_embed",
    }),
    createProvider: async () => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "Local",
        billed: false,
      },
      profiles: [],
    }),
    ...overrides,
  };
}

describe("ModelsPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const snapshot = vi.fn(async () => modelsClient().snapshot());
    render(
      <ModelsPage
        engineClient={engine("unavailable")}
        modelsClient={modelsClient({ snapshot })}
      />,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Models" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to assign model profiles/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save assignments/i })).not.toBeInTheDocument();
    expect(snapshot).not.toHaveBeenCalled();
  });

  it("assigns planner coder reviewer and embedding profiles", async () => {
    const user = userEvent.setup();
    const assign = vi.fn(async (assignments: Record<ModelRole, string>) => assignments);
    render(
      <ModelsPage
        engineClient={engine("ready")}
        modelsClient={modelsClient({ assign })}
      />,
    );

    expect(await screen.findByLabelText(/^planner$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^coder$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^reviewer$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^embedding$/i)).toBeInTheDocument();
    expect(await screen.findByText(/cursor-agent/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save assignments/i }));
    expect(assign).toHaveBeenCalledWith({
      planner: "prof_local",
      coder: "prof_local",
      reviewer: "prof_local",
      embedding: "prof_embed",
    });
  });

  it("registers a detected local endpoint on an empty ready engine then assigns", async () => {
    const user = userEvent.setup();
    const profiles = [
      { id: "prof_planner", displayName: "Local (planner)", role: "planner", billed: false },
      { id: "prof_coder", displayName: "Local (coder)", role: "coder", billed: false },
      { id: "prof_reviewer", displayName: "Local (reviewer)", role: "reviewer", billed: false },
      { id: "prof_embedding", displayName: "Local (embedding)", role: "embedding", billed: false },
    ];
    let registered = false;
    const createProvider = vi.fn(async () => {
      registered = true;
      return {
        provider: {
          id: "prov_local",
          kind: "openai_compatible",
          displayName: "http://127.0.0.1:11434/v1",
          billed: false,
        },
        profiles,
      };
    });
    const assign = vi.fn(async (assignments: Record<ModelRole, string>) => assignments);
    render(
      <ModelsPage
        engineClient={engine("ready")}
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [
              {
                kind: "openai_compatible",
                label: "http://127.0.0.1:11434/v1",
                present: true,
              },
            ],
            profiles: registered ? profiles : [],
            assignments: {
              planner: null,
              coder: null,
              reviewer: null,
              embedding: null,
            },
            embeddingBackend: { kind: "none", modelId: "", displayName: "Sparse only" },
          }),
          createProvider,
          assign,
        })}
      />,
    );

    expect(
      await screen.findByRole("button", { name: /register as provider/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /register as provider/i }));
    expect(createProvider).toHaveBeenCalledWith({
      kind: "openai_compatible",
      displayName: "http://127.0.0.1:11434/v1",
      baseUrl: "http://127.0.0.1:11434/v1",
      billed: false,
    });
    expect(await screen.findByLabelText(/^planner$/i)).toHaveValue("prof_planner");
    await user.click(screen.getByRole("button", { name: /save assignments/i }));
    expect(assign).toHaveBeenCalledWith({
      planner: "prof_planner",
      coder: "prof_coder",
      reviewer: "prof_reviewer",
      embedding: "prof_embedding",
    });
  });

  it("shows which embedding backend is in use", async () => {
    render(
      <ModelsPage engineClient={engine("ready")} modelsClient={modelsClient()} />,
    );

    expect(await screen.findByText(/embedding backend/i)).toBeInTheDocument();
    expect(screen.getByText(/local onnx/i)).toBeInTheDocument();
  });

  it("reloads embedding backend after saving assignments", async () => {
    const user = userEvent.setup();
    let assigned = false;
    const snapshot = vi.fn(async () => ({
      detected: [],
      profiles: [
        { id: "prof_local", displayName: "Local llama3", role: "coder", billed: false },
        { id: "prof_embed", displayName: "Remote embed", role: "embedding", billed: false },
      ],
      assignments: {
        planner: "prof_local",
        coder: "prof_local",
        reviewer: "prof_local",
        embedding: "prof_embed",
      },
      embeddingBackend: assigned
        ? {
            kind: "openai_compatible" as const,
            modelId: "nomic-embed-text",
            displayName: "Remote embed",
          }
        : {
            kind: "onnx" as const,
            modelId: "all-MiniLM-L6-v2",
            displayName: "Local ONNX",
          },
    }));
    const assign = vi.fn(async (assignments: Record<ModelRole, string>) => {
      assigned = true;
      return {
        planner: assignments.planner,
        coder: assignments.coder,
        reviewer: assignments.reviewer,
        embedding: assignments.embedding,
      };
    });
    render(
      <ModelsPage
        engineClient={engine("ready")}
        modelsClient={modelsClient({ snapshot, assign })}
      />,
    );

    expect(await screen.findByText(/local onnx/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save assignments/i }));
    expect(assign).toHaveBeenCalled();
    expect(await screen.findByText(/openai-compatible/i)).toBeInTheDocument();
    expect(snapshot.mock.calls.length).toBeGreaterThan(1);
  });
});
