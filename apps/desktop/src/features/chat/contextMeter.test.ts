// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  CHAT_CONTEXT_OVERHEAD_TOKENS,
  CHAT_CONTEXT_WINDOW_TOKENS,
  chatContextMeterLabel,
  chatContextUsage,
  chatContextWarning,
  estimateTokenCount,
} from "./contextMeter";

describe("estimateTokenCount", () => {
  it("uses a four-characters-per-token estimate and treats empty text as zero", () => {
    expect(estimateTokenCount("")).toBe(0);
    expect(estimateTokenCount("abcd")).toBe(1);
    expect(estimateTokenCount("abcde")).toBe(2);
  });
});

describe("chatContextUsage", () => {
  it("adds overhead and caps the ratio at one", () => {
    const short = chatContextUsage(["hello"]);
    expect(short.window).toBe(CHAT_CONTEXT_WINDOW_TOKENS);
    expect(short.used).toBe(CHAT_CONTEXT_OVERHEAD_TOKENS + estimateTokenCount("hello"));
    expect(short.ratio).toBeLessThan(1);

    const huge = chatContextUsage(["a".repeat(CHAT_CONTEXT_WINDOW_TOKENS * 8)]);
    expect(huge.ratio).toBe(1);
    expect(huge.used).toBeGreaterThan(CHAT_CONTEXT_WINDOW_TOKENS);
  });

  it("uses the orchestrator window when one is provided", () => {
    const usage = chatContextUsage(["hello"], 8_000);
    expect(usage.window).toBe(8_000);
    expect(usage.used).toBe(CHAT_CONTEXT_OVERHEAD_TOKENS + estimateTokenCount("hello"));
  });

  it("falls back to 32000 when the window is missing or zero", () => {
    expect(chatContextUsage(["hello"], 0).window).toBe(CHAT_CONTEXT_WINDOW_TOKENS);
  });
});

describe("chatContextMeterLabel", () => {
  it("names the estimate without a locale-specific thousands separator", () => {
    expect(chatContextMeterLabel({ used: 200, window: 32000, ratio: 200 / 32000 })).toBe(
      "About 200 of 32000 tokens",
    );
  });
});

describe("chatContextWarning", () => {
  it("warns at 80 percent and stays quiet below that", () => {
    expect(chatContextWarning(0.79)).toBeNull();
    expect(chatContextWarning(0.8)).toBe(
      "This chat is getting long. Start a new chat if replies get worse.",
    );
  });
});
