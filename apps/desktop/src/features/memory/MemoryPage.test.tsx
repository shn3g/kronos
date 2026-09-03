// SPDX-License-Identifier: AGPL-3.0-or-later

import { screen } from "@testing-library/react";
import { renderWithEngineConnection } from "../../engine/testUtils";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { MemoryPage, type MemoryClient } from "./MemoryPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

describe("MemoryPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => []);
    renderWithEngineConnection(<MemoryPage
memoryClient={{ list, importLessons: async () => [] }}
      />, engine("unavailable"));

    expect(await screen.findByRole("heading", { level: 1, name: "Memory" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /import as disabled candidates/i }),
    ).not.toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("shows disabled candidate records when the engine is ready", async () => {
    const list: MemoryClient["list"] = async () => [
      {
        id: "lesson-booking-tz",
        kind: "procedural",
        text: "Convert event times to the venue timezone before persist.",
        sourceSha: "1".repeat(40),
        outcome: "neutral",
        confidence: 0,
        helpful: 4,
        harmful: 0,
        status: "disabled_candidate",
        skillId: null,
      },
    ];
    renderWithEngineConnection(<MemoryPage
memoryClient={{ list, importLessons: async () => [] }} />, engine("ready"));

    expect(await screen.findByText(/disabled_candidate/)).toBeInTheDocument();
    expect(screen.getByText(/Convert event times/)).toBeInTheDocument();
  });
});
