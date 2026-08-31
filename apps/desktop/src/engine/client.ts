// SPDX-License-Identifier: AGPL-3.0-or-later

import { probeEngineState, type EngineLocateResult } from "../api/kronosClient";

export type EngineConnectionState =
  | { status: "unavailable" }
  | { status: "starting" }
  | { status: "ready"; version: string }
  | {
      status: "incompatible";
      clientVersion: string;
      engineVersion: string;
    };

export interface EngineClient {
  getState(): Promise<EngineConnectionState>;
}

export interface ProductionEngineClientOptions {
  locate?: () => Promise<EngineLocateResult | null>;
}

export function createProductionEngineClient(
  options: ProductionEngineClientOptions = {},
): EngineClient {
  const locate = options.locate ?? locateEngineFromSidecar;
  return {
    async getState() {
      try {
        const located = await locate();
        if (located === null) {
          return { status: "unavailable" };
        }
        return await probeEngineState({
          baseUrl: located.baseUrl,
          token: located.token,
        });
      } catch {
        return { status: "unavailable" };
      }
    },
  };
}

async function locateEngineFromSidecar(): Promise<EngineLocateResult | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const result = await invoke<EngineLocateResult | null>("engine_connection");
    if (result === null || result.baseUrl.length === 0 || result.token.length === 0) {
      return null;
    }
    return result;
  } catch {
    return null;
  }
}
