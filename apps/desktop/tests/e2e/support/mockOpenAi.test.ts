/** @vitest-environment node */
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  E2E_FINAL_ANSWER,
  openaiChatSse,
  readFileToolFence,
  scriptedAssistantText,
} from "./mockOpenAi";

describe("mock OpenAI script", () => {
  it("scripts a read_file tool fence then a final answer", () => {
    const first = scriptedAssistantText(0);
    expect(first).toBe(readFileToolFence("README.md"));
    expect(first).toContain("```tool");
    expect(first).toContain('"name":"read_file"');
    expect(first).toContain('"path":"README.md"');
    expect(scriptedAssistantText(1)).toBe(E2E_FINAL_ANSWER);
    expect(scriptedAssistantText(1)).not.toContain("```tool");
    expect(scriptedAssistantText(2)).toBe(E2E_FINAL_ANSWER);
  });

  it("wraps replies as OpenAI chat SSE deltas", () => {
    const body = openaiChatSse("hello");
    expect(body).toContain('data: {"choices":[{"delta":{"content":"hello"}}]}');
    expect(body).toContain("data: [DONE]");
  });
});
