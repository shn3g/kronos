import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { EngineClient } from "../../engine/client";
import type { SettingsSection } from "../../shell/routes";
import type { ModelsClient } from "../models/client";
import type { SettingsPageClients } from "./client";
import { SettingsHub } from "./SettingsHub";

function readyEngine(): EngineClient {
  return { getState: async () => ({ status: "ready", version: "0.2.0" }) };
}

function emptyBackend() {
  return { kind: "none" as const, modelId: "", displayName: "Sparse only" };
}

function assignedModels(): ModelsClient {
  return {
    snapshot: async () => ({
      detected: [],
      profiles: [
        {
          id: "prof_local",
          displayName: "Local llama",
          role: "orchestrator",
          billed: false,
          modelId: "llama3",
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
      embeddingBackend: emptyBackend(),
    }),
    assign: async () => ({
      orchestrator: "prof_local",
      planner: "prof_local",
      coder: "prof_local",
      reviewer: "prof_local",
      embedding: "prof_local",
    }),
    createProvider: async () => ({
      provider: { id: "prov_1", kind: "openai_compatible", displayName: "Local", billed: false },
      profiles: [],
    }),
    updateProfile: async (id) => ({
      id,
      displayName: id,
      role: "orchestrator",
      billed: false,
      modelId: "",
      limits: { maxTokens: 0, maxAttempts: 0, timeoutSeconds: 0, costCeiling: 0 },
    }),
  };
}

function quietSettings(): SettingsPageClients {
  return {
    load: async () => ({ otelExport: false, langfuseExport: false }),
    save: async (next) => next,
    doctor: async () => ({ ready: true, findings: [] }),
    backup: async () => ({ path: "", includesSecretStore: false }),
  };
}

function Harness({ initial = "general" }: { initial?: SettingsSection }) {
  const [section, setSection] = useState<SettingsSection>(initial);
  return (
    <SettingsHub
      engineClient={readyEngine()}
      section={section}
      onSection={setSection}
      modelsClient={assignedModels()}
      settingsClient={quietSettings()}
    />
  );
}

describe("SettingsHub", () => {
  it("lists every settings section and switches the visible page", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByRole("navigation", { name: /settings/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^general$/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(await screen.findByRole("heading", { name: /^settings$/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^models$/i }));
    expect(await screen.findByRole("heading", { name: /^models$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^models$/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByRole("heading", { name: /^settings$/i })).not.toBeInTheDocument();
  });
});
