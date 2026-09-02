// SPDX-License-Identifier: AGPL-3.0-or-later

import { DESKTOP_CLIENT_VERSION } from "../../api/kronosClient";
import { isUpdaterSigningConfigured } from "./updaterConfig";

export type UpdateCheckResult =
  | { status: "up-to-date"; currentVersion: string }
  | { status: "available"; version: string; notes: string };

export interface TauriUpdateHandle {
  version: string;
  body?: string | null;
  date?: string | null;
  downloadAndInstall(onEvent?: (event: { event: string }) => void): Promise<void>;
}

export interface AppUpdaterBindings {
  check(): Promise<TauriUpdateHandle | null>;
  relaunch(): Promise<void>;
}

let cachedUpdate: TauriUpdateHandle | null = null;

async function loadProductionBindings(): Promise<AppUpdaterBindings> {
  const [{ check }, { relaunch }] = await Promise.all([
    import("@tauri-apps/plugin-updater"),
    import("@tauri-apps/plugin-process"),
  ]);
  return {
    async check() {
      const update = await check();
      cachedUpdate = update;
      return update;
    },
    relaunch,
  };
}

export function createProductionAppUpdater(
  bindingsLoader: () => Promise<AppUpdaterBindings> = loadProductionBindings,
  pubkeyConfigured: () => boolean = () => isUpdaterSigningConfigured(),
) {
  let bindings: AppUpdaterBindings | null = null;

  async function ensureBindings(): Promise<AppUpdaterBindings> {
    if (!bindings) {
      bindings = await bindingsLoader();
    }
    return bindings;
  }

  return {
    updaterSigningConfigured: pubkeyConfigured,
    async checkForUpdates(): Promise<UpdateCheckResult> {
      const client = await ensureBindings();
      const update = await client.check();
      cachedUpdate = update;
      if (!update) {
        return { status: "up-to-date", currentVersion: DESKTOP_CLIENT_VERSION };
      }
      return {
        status: "available",
        version: update.version,
        notes: update.body?.trim() || `Kronos ${update.version} is available.`,
      };
    },
    async installAndRestart(): Promise<void> {
      const client = await ensureBindings();
      if (!cachedUpdate) {
        throw new Error("no update is ready to install");
      }
      await cachedUpdate.downloadAndInstall();
      await client.relaunch();
    },
  };
}
