// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { UpdatesPage, type UpdatesPageClients } from "./UpdatesPage";

function engine(status: "unavailable" | "starting" | "ready" | "incompatible"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  if (status === "incompatible") {
    return {
      getState: async () => ({
        status: "incompatible",
        clientVersion: "0.1.0",
        engineVersion: "2.0.0",
      }),
    };
  }
  return { getState: async () => ({ status }) };
}

function clients(overrides: Partial<UpdatesPageClients> = {}): UpdatesPageClients {
  return {
    status: async () => ({
      engineVersion: "0.1.0",
      clientVersion: "0.1.0",
      compatible: true,
      signed: false,
      checksumsPresent: true,
      sbomPresent: true,
      provenancePresent: true,
    }),
    rollback: async () => ({ version: "0.1.0" }),
    ...overrides,
  };
}

describe("UpdatesPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const status = vi.fn(async () => clients().status());
    render(
      <UpdatesPage engineClient={engine("unavailable")} updatesClient={clients({ status })} />,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Updates" })).toBeInTheDocument();
    expect(
      screen.getByText(/connect a compatible engine to inspect updates/i),
    ).toBeInTheDocument();
    expect(status).not.toHaveBeenCalled();
  });

  it("refuses incompatible versions and does not claim a signed build", async () => {
    render(<UpdatesPage engineClient={engine("incompatible")} updatesClient={clients()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Updates" })).toBeInTheDocument();
    expect(screen.getByText(/incompatible/i)).toBeInTheDocument();
    expect(screen.queryByText(/^signed$/i)).not.toBeInTheDocument();
  });

  it("shows checksums and unsigned status when ready", async () => {
    render(<UpdatesPage engineClient={engine("ready")} updatesClient={clients()} />);
    expect(await screen.findByText(/0\.1\.0/)).toBeInTheDocument();
    expect(screen.getByText(/not signed/i)).toBeInTheDocument();
    expect(screen.getByText(/checksums/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rollback/i })).toBeInTheDocument();
  });
});
