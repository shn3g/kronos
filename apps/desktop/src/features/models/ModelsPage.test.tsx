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
    }),
    assign: async () => ({
      planner: "prof_local",
      coder: "prof_local",
      reviewer: "prof_local",
      embedding: "prof_embed",
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
});
