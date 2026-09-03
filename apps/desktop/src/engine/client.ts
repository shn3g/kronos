// SPDX-License-Identifier: AGPL-3.0-or-later

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
  readState?: () => Promise<EngineConnectionState | null>;
}

export function createProductionEngineClient(
  options: ProductionEngineClientOptions = {},
): EngineClient {
  const readState = options.readState ?? readStateFromSidecar;
  return {
    async getState() {
      try {
        const state = await readState();
        if (state === null) {
          return { status: "unavailable" };
        }
        return state;
      } catch {
        return { status: "unavailable" };
      }
    },
  };
}

async function readStateFromSidecar(): Promise<EngineConnectionState | null> {
  try {
    const { invoke, isTauri } = await import("@tauri-apps/api/core");
    if (!isTauri()) {
      throw new Error("web build");
    }
    const result = await invoke<EngineConnectionState | null>("engine_state");
    if (result === null) {
      return null;
    }
    return result;
  } catch {
    const { probeEngineState } = await import("../api/kronosClient");
    return probeEngineState({
      baseUrl: "/kronos-engine",
      token: "",
    });
  }
}
