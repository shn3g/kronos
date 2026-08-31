// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { SettingsPage, type SettingsPageClients } from "./SettingsPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function clients(overrides: Partial<SettingsPageClients> = {}): SettingsPageClients {
  return {
    load: async () => ({ otelExport: false, langfuseExport: false }),
    save: async (next) => next,
    doctor: async () => ({ ready: true, findings: ["engine ok"] }),
    backup: async () => ({ path: "C:/tmp/backup", includesSecretStore: false }),
    ...overrides,
  };
}

describe("SettingsPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const load = vi.fn(async () => clients().load());
    render(
      <SettingsPage engineClient={engine("unavailable")} settingsClient={clients({ load })} />,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to change settings/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/bot token/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/private key/i)).not.toBeInTheDocument();
    expect(load).not.toHaveBeenCalled();
  });

  it("shows export toggles and doctor without secret paste fields", async () => {
    render(<SettingsPage engineClient={engine("ready")} settingsClient={clients()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByLabelText(/opentelemetry export/i)).not.toBeChecked();
    expect(screen.getByRole("button", { name: /run doctor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /backup/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/bot token/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/private key/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
