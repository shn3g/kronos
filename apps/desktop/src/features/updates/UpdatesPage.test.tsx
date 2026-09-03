// SPDX-License-Identifier: AGPL-3.0-or-later

import { screen, waitFor } from "@testing-library/react";
import { renderWithEngineConnection } from "../../engine/testUtils";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DESKTOP_CLIENT_VERSION } from "../../api/kronosClient";
import type { EngineClient } from "../../engine/client";
import { UpdatesPage, type UpdatesPageClients } from "./UpdatesPage";

function engine(status: "unavailable" | "starting" | "ready" | "incompatible"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: DESKTOP_CLIENT_VERSION }) };
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
      engineVersion: DESKTOP_CLIENT_VERSION,
      clientVersion: DESKTOP_CLIENT_VERSION,
      compatible: true,
      signed: true,
      checksumsPresent: true,
      sbomPresent: true,
      provenancePresent: true,
    }),
    rollback: async () => ({ version: "0.1.0" }),
    updaterSigningConfigured: () => true,
    checkForUpdates: async () => ({ status: "up-to-date", currentVersion: DESKTOP_CLIENT_VERSION }),
    installAndRestart: async () => undefined,
    ...overrides,
  };
}

describe("UpdatesPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const status = vi.fn(async () => clients().status());
    renderWithEngineConnection(<UpdatesPage
updatesClient={clients({ status })} />, engine("unavailable"));
    expect(await screen.findByRole("heading", { level: 1, name: "Updates" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(status).not.toHaveBeenCalled();
  });

  it("refuses incompatible versions and does not claim a signed build", async () => {
    renderWithEngineConnection(<UpdatesPage
updatesClient={clients()} />, engine("incompatible"));
    expect(await screen.findByRole("heading", { level: 1, name: "Updates" })).toBeInTheDocument();
    expect(screen.getByText(/incompatible/i)).toBeInTheDocument();
    expect(screen.queryByText(/^signed$/i)).not.toBeInTheDocument();
  });

  it("shows checksums, provenance warning, and rollback when ready", async () => {
    renderWithEngineConnection(<UpdatesPage
updatesClient={clients()} />, engine("ready"));
    expect(
      await screen.findByText(
        `Engine ${DESKTOP_CLIENT_VERSION}. Desktop ${DESKTOP_CLIENT_VERSION}.`,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/smartscreen/i)).toBeInTheDocument();
    expect(screen.getByText(/checksums/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rollback/i })).toBeInTheDocument();
  });

  it("disables check for updates when signing is not configured", async () => {
    renderWithEngineConnection(<UpdatesPage
updatesClient={clients({ updaterSigningConfigured: () => false })}
      />, engine("ready"));
    expect(await screen.findByText(/updates are not signed yet/i)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: /check for updates/i });
    expect(button).toBeDisabled();
  });

  it("shows up to date after checking", async () => {
    const user = userEvent.setup();
    const checkForUpdates = vi.fn(async () => ({
      status: "up-to-date" as const,
      currentVersion: DESKTOP_CLIENT_VERSION,
    }));
    renderWithEngineConnection(<UpdatesPage
updatesClient={clients({ checkForUpdates })}
      />, engine("ready"));
    await user.click(await screen.findByRole("button", { name: /check for updates/i }));
    await waitFor(() => expect(checkForUpdates).toHaveBeenCalled());
    expect(await screen.findByText(/you are on the latest version/i)).toBeInTheDocument();
  });

  it("shows update available with notes and install action", async () => {
    const user = userEvent.setup();
    const checkForUpdates = vi.fn(async () => ({
      status: "available" as const,
      version: "0.5.0",
      notes: "One-click install and signed updates.",
    }));
    const installAndRestart = vi.fn(async () => undefined);
    renderWithEngineConnection(<UpdatesPage
updatesClient={clients({ checkForUpdates, installAndRestart })}
      />, engine("ready"));
    await user.click(await screen.findByRole("button", { name: /check for updates/i }));
    expect(await screen.findByText(/0\.5\.0 is available/i)).toBeInTheDocument();
    expect(screen.getByText(/one-click install and signed updates/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /install and restart/i }));
    expect(installAndRestart).toHaveBeenCalled();
  });

  it("shows install errors", async () => {
    const user = userEvent.setup();
    const checkForUpdates = vi.fn(async () => ({
      status: "available" as const,
      version: "0.5.0",
      notes: "Notes",
    }));
    const installAndRestart = vi.fn(async () => {
      throw new Error("signature verification failed");
    });
    renderWithEngineConnection(<UpdatesPage
updatesClient={clients({ checkForUpdates, installAndRestart })}
      />, engine("ready"));
    await user.click(await screen.findByRole("button", { name: /check for updates/i }));
    await user.click(await screen.findByRole("button", { name: /install and restart/i }));
    expect(await screen.findByText(/signature verification failed/i)).toBeInTheDocument();
  });
});
