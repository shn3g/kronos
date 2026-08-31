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

export function createProductionEngineClient(): EngineClient {
  return {
    async getState() {
      // No sidecar in this milestone. Fail closed instead of reporting ready.
      return { status: "unavailable" };
    },
  };
}
