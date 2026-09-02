// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";
import { createProductionAppUpdater, type UpdateCheckResult } from "./appUpdater";

export interface UpdateStatusView {
  engineVersion: string;
  clientVersion: string;
  compatible: boolean;
  signed: boolean;
  checksumsPresent: boolean;
  sbomPresent: boolean;
  provenancePresent: boolean;
}

export interface UpdatesPageClients {
  status(): Promise<UpdateStatusView>;
  rollback(): Promise<{ version: string }>;
  updaterSigningConfigured(): boolean;
  checkForUpdates(): Promise<UpdateCheckResult>;
  installAndRestart(): Promise<void>;
}

export function createProductionUpdatesClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): UpdatesPageClients {
  const updater = createProductionAppUpdater();
  return {
    async status() {
      const payload = await jsonRequest(request, "GET", "/ops/updates");
      return {
        engineVersion: stringField(payload, "engine_version"),
        clientVersion: stringField(payload, "client_version"),
        compatible: payload.compatible === true,
        signed: payload.signed === true,
        checksumsPresent: payload.checksums_present === true,
        sbomPresent: payload.sbom_present === true,
        provenancePresent: payload.provenance_present === true,
      };
    },
    async rollback() {
      const payload = await jsonRequest(request, "POST", "/ops/rollback");
      return { version: stringField(payload, "version") };
    },
    updaterSigningConfigured: updater.updaterSigningConfigured,
    checkForUpdates: updater.checkForUpdates,
    installAndRestart: updater.installAndRestart,
  };
}

async function jsonRequest(
  request: (method: string, path: string, body?: unknown) => Promise<EngineJsonResponse>,
  method: string,
  path: string,
  body?: unknown,
): Promise<Record<string, unknown>> {
  const response = await request(method, path, body);
  if (response.status < 200 || response.status >= 300) {
    throw new Error(`engine request failed: ${response.status}`);
  }
  try {
    return JSON.parse(response.body) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
