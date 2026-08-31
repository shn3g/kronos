// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient, EngineConnectionState } from "./client";

interface EngineStatusProps {
  client: EngineClient;
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

export function EngineStatus({ client }: EngineStatusProps) {
  const [state, setState] = useState<EngineConnectionState>({
    status: "unavailable",
  });

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void client
        .getState()
        .then((next) => {
          if (!cancelled) {
            setState(next);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setState({ status: "unavailable" });
          }
        });
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [client]);

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
