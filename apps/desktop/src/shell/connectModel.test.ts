import { describe, expect, it } from "vitest";
import {
  assignmentsFromCreatedProfiles,
  cursorCliDetected,
  displayNameFromEndpointLabel,
  billedFromBaseUrl,
  localOpenAiProviderDraft,
  MODEL_URL_PRESETS,
  parseModelSetupLine,
  pickLocalOpenAiEndpoint,
  workerCliDetected,
} from "./connectModel";

describe("pickLocalOpenAiEndpoint", () => {
  it("returns the first present OpenAI-compatible endpoint", () => {
    const picked = pickLocalOpenAiEndpoint([
      { kind: "cursor_cli", label: "cursor-agent", present: true },
      { kind: "openai_compatible", label: "http://127.0.0.1:11434/v1", present: true },
    ]);
    expect(picked?.label).toBe("http://127.0.0.1:11434/v1");
  });

  it("returns null when no local OpenAI server is present", () => {
    expect(
      pickLocalOpenAiEndpoint([{ kind: "cursor_cli", label: "cursor-agent", present: true }]),
    ).toBeNull();
  });
});

describe("cursorCliDetected", () => {
  it("is true only when cursor-agent is present", () => {
    expect(
      cursorCliDetected([{ kind: "cursor_cli", label: "cursor-agent", present: true }]),
    ).toBe(true);
    expect(cursorCliDetected([])).toBe(false);
  });
});

describe("workerCliDetected", () => {
  it("recognizes Cursor, OpenCode, and Claude Code workers", () => {
    expect(
      workerCliDetected([{ kind: "claude_code_cli", label: "claude", present: true }]),
    ).toBe(true);
    expect(
      workerCliDetected([{ kind: "opencode_cli", label: "opencode", present: true }]),
    ).toBe(true);
    expect(
      workerCliDetected([{ kind: "openai_compatible", label: "http://x", present: true }]),
    ).toBe(false);
  });
});

describe("localOpenAiProviderDraft", () => {
  it("names Ollama and LM Studio from the port", () => {
    expect(displayNameFromEndpointLabel("http://127.0.0.1:11434/v1")).toBe("Ollama");
    expect(
      localOpenAiProviderDraft({
        kind: "openai_compatible",
        label: "http://127.0.0.1:1234/v1",
        present: true,
      }),
    ).toEqual({
      kind: "openai_compatible",
      displayName: "LM Studio",
      baseUrl: "http://127.0.0.1:1234/v1",
      billed: false,
    });
  });
});

describe("billedFromBaseUrl", () => {
  it("treats loopback as local and hosted APIs as billed", () => {
    expect(billedFromBaseUrl("http://127.0.0.1:11434/v1")).toBe(false);
    expect(billedFromBaseUrl("https://api.openai.com/v1")).toBe(true);
    expect(billedFromBaseUrl("https://opencode.ai/zen/v1")).toBe(true);
  });
});

describe("MODEL_URL_PRESETS", () => {
  it("matches the five Models page provider presets", () => {
    expect(MODEL_URL_PRESETS.map((item) => item.label)).toEqual([
      "OpenAI",
      "OpenRouter",
      "OpenCode Zen",
      "Ollama",
      "LM Studio",
    ]);
  });
});

describe("assignmentsFromCreatedProfiles", () => {
  it("fills missing roles including orchestrator from the planner profile", () => {
    expect(assignmentsFromCreatedProfiles([{ id: "prof_1", role: "planner" }])).toEqual({
      orchestrator: "prof_1",
      planner: "prof_1",
      coder: "prof_1",
      reviewer: "prof_1",
      embedding: "prof_1",
    });
  });

  it("keeps an explicit orchestrator profile", () => {
    expect(
      assignmentsFromCreatedProfiles([
        { id: "orch_1", role: "orchestrator" },
        { id: "plan_1", role: "planner" },
      ]),
    ).toEqual({
      orchestrator: "orch_1",
      planner: "plan_1",
      coder: "orch_1",
      reviewer: "orch_1",
      embedding: "orch_1",
    });
  });

  it("returns null when the provider created no profiles", () => {
    expect(assignmentsFromCreatedProfiles([])).toBeNull();
  });
});

describe("parseModelSetupLine", () => {
  it("parses OpenAI with model and key", () => {
    const draft = parseModelSetupLine("openai gpt-4o key sk-test1234567890");
    expect(draft).toEqual({
      kind: "openai_compatible",
      displayName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      billed: true,
      apiKey: "sk-test1234567890",
      modelId: "gpt-4o",
    });
  });

  it("parses Ollama without a key", () => {
    const draft = parseModelSetupLine("use ollama llama3");
    expect(draft?.displayName).toBe("Ollama");
    expect(draft?.baseUrl).toContain("11434");
    expect(draft?.apiKey).toBeNull();
    expect(draft?.modelId).toBe("llama3");
  });

  it("returns null for empty noise", () => {
    expect(parseModelSetupLine("hello")).toBeNull();
  });
});
