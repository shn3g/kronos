// SPDX-License-Identifier: AGPL-3.0-or-later

export type StreamPhase = "idle" | "streaming" | "tool" | "done" | "error";

export const STREAM_STATUS_SETTLE_MS = 2000;

export function streamStatusMessage(phase: StreamPhase, toolLabel?: string): string | null {
  if (phase === "streaming") {
    return "Streaming reply.";
  }
  if (phase === "tool") {
    return toolLabel ? `${toolLabel} · running.` : "Running a tool.";
  }
  if (phase === "done") {
    return "Turn finished.";
  }
  if (phase === "error") {
    return "Message failed.";
  }
  return null;
}
