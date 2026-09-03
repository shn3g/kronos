// SPDX-License-Identifier: AGPL-3.0-or-later

import type { EngineConnectionState } from "./client";
import { DESKTOP_CLIENT_VERSION } from "../api/kronosClient";

interface EngineStatusProps {
  state: EngineConnectionState;
}

function labelFor(state: EngineConnectionState): string {
  switch (state.status) {
    case "unavailable":
      return "Kronos stopped. Restarting the local service…";
    case "starting":
      return "Starting Kronos…";
    case "ready":
      return `Kronos ready. Desktop ${DESKTOP_CLIENT_VERSION}. Service ${state.version}.`;
    case "incompatible":
      return `Version mismatch. Desktop ${state.clientVersion} cannot use service ${state.engineVersion}. Install matching builds.`;
  }
}

export function EngineStatus({ state }: EngineStatusProps) {
  return (
    <div
      className="engine-status"
      role="status"
      aria-live="polite"
      data-engine-status={state.status}
    >
      <span className="engine-status__mark" aria-hidden="true" />
      <span className="engine-status__copy">{labelFor(state)}</span>
    </div>
  );
}
