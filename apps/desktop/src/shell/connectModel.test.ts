// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  assignmentsFromCreatedProfiles,
  cursorCliDetected,
  displayNameFromEndpointLabel,
  billedFromBaseUrl,
  localOpenAiProviderDraft,
  pickLocalOpenAiEndpoint,
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
  it("treats loopback as local and OpenAI as billed", () => {
    expect(billedFromBaseUrl("http://127.0.0.1:11434/v1")).toBe(false);
    expect(billedFromBaseUrl("https://api.openai.com/v1")).toBe(true);
  });
});

describe("assignmentsFromCreatedProfiles", () => {
  it("fills missing roles from the planner profile", () => {
    expect(
      assignmentsFromCreatedProfiles([{ id: "prof_1", role: "planner" }]),
    ).toEqual({
      planner: "prof_1",
      coder: "prof_1",
      reviewer: "prof_1",
      embedding: "prof_1",
    });
  });

  it("returns null when the provider created no profiles", () => {
    expect(assignmentsFromCreatedProfiles([])).toBeNull();
  });
});
