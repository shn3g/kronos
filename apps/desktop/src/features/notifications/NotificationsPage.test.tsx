// SPDX-License-Identifier: AGPL-3.0-or-later

import { screen } from "@testing-library/react";
import { renderWithEngineConnection } from "../../engine/testUtils";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../engine/client";
import { NotificationsPage, type NotificationsPageClients } from "./NotificationsPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function clients(overrides: Partial<NotificationsPageClients> = {}): NotificationsPageClients {
  return {
    list: async () => [
      { id: "alert_1", title: "Index degraded", detail: "corrupt cache", severity: "pause" },
    ],
    ...overrides,
  };
}

describe("NotificationsPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const list = vi.fn(async () => clients().list());
    renderWithEngineConnection(<NotificationsPage
notificationsClient={clients({ list })}
      />, engine("unavailable"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Notifications" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("lists pause alerts when the engine is ready", async () => {
    renderWithEngineConnection(<NotificationsPage
notificationsClient={clients()} />, engine("ready"));
    expect(await screen.findByText("Index degraded")).toBeInTheDocument();
    expect(screen.getByText(/corrupt cache/i)).toBeInTheDocument();
  });
});
