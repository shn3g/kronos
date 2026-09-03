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

/**
 * Tail of the sidecar and engine log files, for the "stopped unexpectedly" gate.
 * Resolves to null in the browser preview or when no log text is available.
 */
export async function engineCrashLog(): Promise<string | null> {
  try {
    const { invoke, isTauri } = await import("@tauri-apps/api/core");
    if (!isTauri()) {
      return null;
    }
    const text = await invoke<string | null>("engine_crash_log");
    if (typeof text !== "string" || text.trim() === "") {
      return null;
    }
    return text;
  } catch {
    return null;
  }
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
