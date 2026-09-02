// SPDX-License-Identifier: AGPL-3.0-or-later

export const CHAT_CONTEXT_WINDOW_TOKENS = 32_000;
export const CHAT_CONTEXT_OVERHEAD_TOKENS = 200;

export interface ChatContextUsage {
  used: number;
  window: number;
  ratio: number;
}

export function estimateTokenCount(text: string): number {
  if (text.length === 0) {
    return 0;
  }
  return Math.max(1, Math.floor((text.length + 3) / 4));
}

export function chatContextUsage(
  parts: readonly string[],
  windowTokens: number = CHAT_CONTEXT_WINDOW_TOKENS,
): ChatContextUsage {
  const used = CHAT_CONTEXT_OVERHEAD_TOKENS + estimateTokenCount(parts.join(""));
  const window = windowTokens > 0 ? windowTokens : CHAT_CONTEXT_WINDOW_TOKENS;
  return {
    used,
    window,
    ratio: Math.min(1, used / window),
  };
}

export function chatContextMeterLabel(usage: ChatContextUsage): string {
  return `About ${usage.used} of ${usage.window} tokens`;
}

export function chatContextWarning(ratio: number): string | null {
  if (ratio < 0.8) {
    return null;
  }
  return "This chat is getting long. Start a new chat if replies get worse.";
}
