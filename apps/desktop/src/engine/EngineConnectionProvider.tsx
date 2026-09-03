// SPDX-License-Identifier: AGPL-3.0-or-later

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { EngineClient, EngineConnectionState } from "./client";

const ACTIVE_POLL_MS = 1500;
const HIDDEN_POLL_MS = 10_000;

export interface EngineConnectionContextValue {
  state: EngineConnectionState;
  engineReady: boolean;
}

const EngineConnectionContext = createContext<EngineConnectionContextValue | null>(null);

interface EngineConnectionProviderProps {
  engineClient: EngineClient;
  children: ReactNode;
}

export function EngineConnectionProvider({
  engineClient,
  children,
}: EngineConnectionProviderProps) {
  const [state, setState] = useState<EngineConnectionState>({ status: "starting" });

  useEffect(() => {
    let cancelled = false;
    let intervalId: number | undefined;

    const poll = () => {
      void engineClient.getState().then(
        (next) => {
          if (!cancelled) {
            setState(next);
          }
        },
        () => {
          if (!cancelled) {
            setState({ status: "unavailable" });
          }
        },
      );
    };

    const schedule = () => {
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
      const intervalMs = document.hidden ? HIDDEN_POLL_MS : ACTIVE_POLL_MS;
      intervalId = window.setInterval(poll, intervalMs);
    };

    const onVisibilityChange = () => {
      poll();
      schedule();
    };

    poll();
    schedule();
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [engineClient]);

  const value = useMemo(
    (): EngineConnectionContextValue => ({
      state,
      engineReady: state.status === "ready",
    }),
    [state],
  );

  return (
    <EngineConnectionContext.Provider value={value}>{children}</EngineConnectionContext.Provider>
  );
}

export function useEngineConnection(): EngineConnectionContextValue {
  const value = useContext(EngineConnectionContext);
  if (value === null) {
    throw new Error("useEngineConnection must be used within EngineConnectionProvider");
  }
  return value;
}
