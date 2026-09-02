// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { ModelsPage, type ModelsClient } from "./ModelsPage";
import type { ModelProfileOption, ModelRole, ProfileUpdate, ResourceLimits } from "./client";

const DEFAULT_LIMITS: ResourceLimits = {
  maxTokens: 4096,
  maxAttempts: 3,
  timeoutSeconds: 120,
  costCeiling: 0,
  contextWindow: 32000,
};

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function profile(
  id: string,
  displayName: string,
  role: string,
  extras: Partial<ModelProfileOption> = {},
): ModelProfileOption {
  return {
    id,
    displayName,
    role,
    billed: false,
    modelId: "local-model",
    limits: DEFAULT_LIMITS,
    ...extras,
  };
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
        profile("prof_local", "Local llama3", "coder"),
        profile("prof_embed", "Local embed", "embedding"),
      ],
      assignments: {
        orchestrator: "prof_local",
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
      orchestrator: "prof_local",
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
    updateProfile: async (id, patch) => ({
      id,
      displayName: "Local llama3",
      role: "coder",
      billed: false,
      modelId: patch.modelId,
      limits: patch.limits,
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

  it("assigns orchestrator planner coder reviewer and embedding profiles", async () => {
    const user = userEvent.setup();
    const assign = vi.fn(async (assignments: Record<ModelRole, string>) => assignments);
    render(
      <ModelsPage
        engineClient={engine("ready")}
        modelsClient={modelsClient({ assign })}
      />,
    );

    expect(await screen.findByLabelText(/^orchestrator$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^planner$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^coder$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^reviewer$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^embedding$/i)).toBeInTheDocument();
    expect(await screen.findByText(/cursor-agent/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save assignments/i }));
    expect(assign).toHaveBeenCalledWith({
      orchestrator: "prof_local",
      planner: "prof_local",
      coder: "prof_local",
      reviewer: "prof_local",
      embedding: "prof_embed",
    });
  });

  it("registers a detected local endpoint on an empty ready engine then assigns", async () => {
    const user = userEvent.setup();
    const profiles = [
      profile("prof_orchestrator", "Local (orchestrator)", "orchestrator"),
      profile("prof_planner", "Local (planner)", "planner"),
      profile("prof_coder", "Local (coder)", "coder"),
      profile("prof_reviewer", "Local (reviewer)", "reviewer"),
      profile("prof_embedding", "Local (embedding)", "embedding"),
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
              orchestrator: null,
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
      orchestrator: "prof_orchestrator",
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
        profile("prof_local", "Local llama3", "coder"),
        profile("prof_embed", "Remote embed", "embedding"),
      ],
      assignments: {
        orchestrator: "prof_local",
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
        orchestrator: assignments.orchestrator,
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

  it("pre-fills OpenAI and Ollama presets without bundling a key", async () => {
    const user = userEvent.setup();
    const createProvider = vi.fn(async () => ({
      provider: {
        id: "prov_openai",
        kind: "openai_compatible",
        displayName: "OpenAI",
        billed: true,
      },
      profiles: [],
    }));
    render(
      <ModelsPage
        engineClient={engine("ready")}
        modelsClient={modelsClient({ createProvider })}
      />,
    );

    expect(await screen.findByRole("button", { name: /^openai$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^openrouter$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /opencode zen/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^ollama$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /lm studio/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^openai$/i }));
    expect(screen.getByLabelText(/base url/i)).toHaveValue("https://api.openai.com/v1");
    expect(screen.getByLabelText(/display name/i)).toHaveValue("OpenAI");
    expect(screen.getByLabelText(/suggested model/i)).toHaveValue("gpt-4o-mini");
    const billed = screen.getByLabelText(/billed/i);
    expect(billed).toBeChecked();
    await user.type(screen.getByLabelText(/api key/i), "sk-user-paste");
    await user.click(screen.getByRole("button", { name: /create provider/i }));
    expect(createProvider).toHaveBeenCalledWith({
      kind: "openai_compatible",
      displayName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      billed: true,
      apiKey: "sk-user-paste",
      modelId: "gpt-4o-mini",
    });
    await user.click(screen.getByRole("button", { name: /^ollama$/i }));
    expect(screen.getByLabelText(/base url/i)).toHaveValue("http://127.0.0.1:11434/v1");
    expect(screen.getByLabelText(/billed/i)).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: /^openrouter$/i }));
    expect(screen.getByLabelText(/base url/i)).toHaveValue("https://openrouter.ai/api/v1");
    expect(screen.getByLabelText(/billed/i)).toBeChecked();
    await user.click(screen.getByRole("button", { name: /opencode zen/i }));
    expect(screen.getByLabelText(/base url/i)).toHaveValue("https://opencode.ai/zen/v1");
    expect(screen.getByLabelText(/billed/i)).toBeChecked();
    await user.click(screen.getByRole("button", { name: /lm studio/i }));
    expect(screen.getByLabelText(/base url/i)).toHaveValue("http://127.0.0.1:1234/v1");
    expect(screen.getByLabelText(/billed/i)).not.toBeChecked();
  });

  it("shows editable cost ceiling and max tokens for a profile", async () => {
    const user = userEvent.setup();
    const updateProfile = vi.fn(async (id: string, patch: ProfileUpdate) =>
      profile("prof_local", "Local llama3", "coder", {
        id,
        billed: true,
        modelId: patch.modelId,
        limits: patch.limits,
      }),
    );
    render(
      <ModelsPage
        engineClient={engine("ready")}
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [],
            profiles: [
              {
                id: "prof_local",
                displayName: "Local llama3",
                role: "coder",
                billed: true,
                modelId: "gpt-4o-mini",
                limits: {
                  maxTokens: 4096,
                  maxAttempts: 3,
                  timeoutSeconds: 120,
                  costCeiling: 0,
                  contextWindow: 32000,
                },
              },
            ],
            assignments: {
              orchestrator: "prof_local",
              planner: "prof_local",
              coder: "prof_local",
              reviewer: "prof_local",
              embedding: "prof_local",
            },
            embeddingBackend: { kind: "none", modelId: "", displayName: "Sparse only" },
          }),
          updateProfile,
        })}
      />,
    );

    expect(await screen.findByLabelText(/cost ceiling/i)).toHaveValue(0);
    expect(screen.getByLabelText(/max tokens/i)).toHaveValue(4096);
    await user.clear(screen.getByLabelText(/cost ceiling/i));
    await user.type(screen.getByLabelText(/cost ceiling/i), "5");
    await user.click(screen.getByRole("button", { name: /save profile/i }));
    expect(updateProfile).toHaveBeenCalledWith(
      "prof_local",
      expect.objectContaining({
        modelId: "gpt-4o-mini",
        limits: expect.objectContaining({ costCeiling: 5, maxTokens: 4096 }),
      }),
    );
  });
});
