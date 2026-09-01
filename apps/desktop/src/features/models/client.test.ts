/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionModelsClient } from "./client";

describe("createProductionModelsClient", () => {
  it("maps assignments from the engine JSON proxy", async () => {
    const client = createProductionModelsClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/models");
      return {
        status: 200,
        body: JSON.stringify({
          detected: [{ kind: "cursor_cli", label: "cursor-agent", present: true }],
          profiles: [
            {
              id: "prof_local",
              display_name: "Local llama3",
              role: "coder",
              billed: false,
            },
          ],
          assignments: {
            orchestrator: "prof_local",
            planner: "prof_local",
            coder: "prof_local",
            reviewer: "prof_local",
            embedding: "prof_local",
          },
        }),
      };
    });

    await expect(client.snapshot()).resolves.toEqual({
      detected: [{ kind: "cursor_cli", label: "cursor-agent", present: true }],
      profiles: [
        {
          id: "prof_local",
          displayName: "Local llama3",
          role: "coder",
          billed: false,
          modelId: "",
          limits: { maxTokens: 0, maxAttempts: 0, timeoutSeconds: 0, costCeiling: 0 },
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
    });
  });

  it("maps embedding_backend from GET /models", async () => {
    const client = createProductionModelsClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/models");
      return {
        status: 200,
        body: JSON.stringify({
          detected: [],
          profiles: [],
          assignments: { orchestrator: null, planner: null, coder: null, reviewer: null, embedding: null },
          embedding_backend: {
            kind: "onnx",
            model_id: "all-MiniLM-L6-v2",
            display_name: "Local ONNX",
          },
        }),
      };
    });

    await expect(client.snapshot()).resolves.toEqual({
      detected: [],
      profiles: [],
      assignments: { orchestrator: null, planner: null, coder: null, reviewer: null, embedding: null },
      embeddingBackend: {
        kind: "onnx",
        modelId: "all-MiniLM-L6-v2",
        displayName: "Local ONNX",
      },
    });
  });

  it("saves role assignments through the engine JSON proxy", async () => {
    const client = createProductionModelsClient(async (method, path, body) => {
      expect(method).toBe("PUT");
      expect(path).toBe("/models/assignments");
      expect(body).toEqual({
        orchestrator: "prof_a",
        planner: "prof_a",
        coder: "prof_a",
        reviewer: "prof_a",
        embedding: "prof_b",
      });
      return {
        status: 200,
        body: JSON.stringify({
          assignments: {
            orchestrator: "prof_a",
            planner: "prof_a",
            coder: "prof_a",
            reviewer: "prof_a",
            embedding: "prof_b",
          },
        }),
      };
    });

    await expect(
      client.assign({
        orchestrator: "prof_a",
        planner: "prof_a",
        coder: "prof_a",
        reviewer: "prof_a",
        embedding: "prof_b",
      }),
    ).resolves.toEqual({
      orchestrator: "prof_a",
      planner: "prof_a",
      coder: "prof_a",
      reviewer: "prof_a",
      embedding: "prof_b",
    });
  });

  it("sends model_id when creating a provider from a preset", async () => {
    const client = createProductionModelsClient(async (method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/models/providers");
      expect(body).toEqual({
        kind: "openai_compatible",
        display_name: "OpenAI",
        base_url: "https://api.openai.com/v1",
        billed: true,
        api_key: "sk-user-paste",
        model_id: "gpt-4o-mini",
      });
      return {
        status: 200,
        body: JSON.stringify({
          provider: {
            id: "prov_1",
            kind: "openai_compatible",
            display_name: "OpenAI",
            billed: true,
          },
          profiles: [
            {
              id: "prof_coder",
              display_name: "OpenAI (coder)",
              role: "coder",
              billed: true,
              model_id: "gpt-4o-mini",
            },
          ],
        }),
      };
    });

    await expect(
      client.createProvider({
        kind: "openai_compatible",
        displayName: "OpenAI",
        baseUrl: "https://api.openai.com/v1",
        billed: true,
        apiKey: "sk-user-paste",
        modelId: "gpt-4o-mini",
      }),
    ).resolves.toEqual({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "OpenAI",
        billed: true,
      },
      profiles: [
        {
          id: "prof_coder",
          displayName: "OpenAI (coder)",
          role: "coder",
          billed: true,
          modelId: "gpt-4o-mini",
          limits: { maxTokens: 0, maxAttempts: 0, timeoutSeconds: 0, costCeiling: 0 },
        },
      ],
    });
  });

  it("registers a local provider through POST /models/providers", async () => {
    const client = createProductionModelsClient(async (method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/models/providers");
      expect(body).toEqual({
        kind: "openai_compatible",
        display_name: "http://127.0.0.1:11434/v1",
        base_url: "http://127.0.0.1:11434/v1",
        billed: false,
      });
      return {
        status: 200,
        body: JSON.stringify({
          provider: {
            id: "prov_1",
            kind: "openai_compatible",
            display_name: "http://127.0.0.1:11434/v1",
            billed: false,
          },
          profiles: [
            {
              id: "prof_coder",
              display_name: "Local (coder)",
              role: "coder",
              billed: false,
            },
          ],
        }),
      };
    });

    await expect(
      client.createProvider({
        kind: "openai_compatible",
        displayName: "http://127.0.0.1:11434/v1",
        baseUrl: "http://127.0.0.1:11434/v1",
        billed: false,
      }),
    ).resolves.toEqual({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "http://127.0.0.1:11434/v1",
        billed: false,
      },
      profiles: [
        {
          id: "prof_coder",
          displayName: "Local (coder)",
          role: "coder",
          billed: false,
          modelId: "",
          limits: { maxTokens: 0, maxAttempts: 0, timeoutSeconds: 0, costCeiling: 0 },
        },
      ],
    });
  });

  it("updates model_id and limits through PUT /models/profiles/{id}", async () => {
    const client = createProductionModelsClient(async (method, path, body) => {
      expect(method).toBe("PUT");
      expect(path).toBe("/models/profiles/prof_coder");
      expect(body).toEqual({
        model_id: "llama3.1",
        limits: {
          max_tokens: 2048,
          max_attempts: 3,
          timeout_seconds: 60,
          cost_ceiling: 1.5,
        },
      });
      return {
        status: 200,
        body: JSON.stringify({
          id: "prof_coder",
          display_name: "Local (coder)",
          role: "coder",
          billed: false,
          model_id: "llama3.1",
          limits: {
            max_tokens: 2048,
            max_attempts: 3,
            timeout_seconds: 60,
            cost_ceiling: 1.5,
          },
        }),
      };
    });

    await expect(
      client.updateProfile("prof_coder", {
        modelId: "llama3.1",
        limits: {
          maxTokens: 2048,
          maxAttempts: 3,
          timeoutSeconds: 60,
          costCeiling: 1.5,
        },
      }),
    ).resolves.toEqual({
      id: "prof_coder",
      displayName: "Local (coder)",
      role: "coder",
      billed: false,
      modelId: "llama3.1",
      limits: {
        maxTokens: 2048,
        maxAttempts: 3,
        timeoutSeconds: 60,
        costCeiling: 1.5,
      },
    });
  });
});
