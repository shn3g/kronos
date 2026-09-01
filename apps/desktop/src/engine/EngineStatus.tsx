// SPDX-License-Identifier: AGPL-3.0-or-later

import type { EngineConnectionState } from "./client";

interface EngineStatusProps {
  state: EngineConnectionState;
}

function labelFor(state: EngineConnectionState): string {
  switch (state.status) {
    case "unavailable":
      return "Engine unavailable. The local engine is not connected.";
    case "starting":
      return "Engine starting. Waiting for the local engine.";
    case "ready":
      return `Engine ready. Version ${state.version}.`;
    case "incompatible":
      return `Incompatible engine version. Desktop ${state.clientVersion} cannot use engine ${state.engineVersion}.`;
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
