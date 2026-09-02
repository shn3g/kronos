// SPDX-License-Identifier: AGPL-3.0-or-later

/** @vitest-environment node */

import { describe, expect, it, vi } from "vitest";
import { DESKTOP_CLIENT_VERSION } from "../../api/kronosClient";
import { createProductionAppUpdater } from "./appUpdater";

describe("createProductionAppUpdater", () => {
  it("reports signing disabled when pubkey is empty", () => {
    const updater = createProductionAppUpdater(
      async () => ({
        check: async () => null,
        relaunch: async () => undefined,
      }),
      () => false,
    );
    expect(updater.updaterSigningConfigured()).toBe(false);
  });

  it("returns up to date when no update is available", async () => {
    const updater = createProductionAppUpdater(async () => ({
      check: async () => null,
      relaunch: async () => undefined,
    }));
    await expect(updater.checkForUpdates()).resolves.toEqual({
      status: "up-to-date",
      currentVersion: DESKTOP_CLIENT_VERSION,
    });
  });

  it("installs and relaunches when an update was checked", async () => {
    const downloadAndInstall = vi.fn(async () => undefined);
    const relaunch = vi.fn(async () => undefined);
    const updater = createProductionAppUpdater(async () => ({
      check: async () => ({
        version: "0.5.0",
        body: "Signed updates",
        downloadAndInstall,
      }),
      relaunch,
    }));
    await updater.checkForUpdates();
    await updater.installAndRestart();
    expect(downloadAndInstall).toHaveBeenCalled();
    expect(relaunch).toHaveBeenCalled();
  });
});
