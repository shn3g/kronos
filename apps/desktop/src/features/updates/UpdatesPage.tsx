// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionUpdatesClient,
  type UpdateStatusView,
  type UpdatesPageClients,
} from "./client";

export type { UpdatesPageClients } from "./client";

interface UpdatesPageProps {
  engineClient: EngineClient;
  updatesClient?: UpdatesPageClients;
}

const productionUpdates = createProductionUpdatesClient();

export function UpdatesPage({ engineClient, updatesClient }: UpdatesPageProps) {
  const client = updatesClient ?? productionUpdates;
  const [engineStatus, setEngineStatus] = useState<"unavailable" | "starting" | "ready" | "incompatible">(
    "unavailable",
  );
  const [status, setStatus] = useState<UpdateStatusView | null>(null);
  const [rolled, setRolled] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engineClient.getState().then((state) => {
        if (!cancelled) {
          setEngineStatus(state.status);
        }
      });
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engineClient]);

  useEffect(() => {
    if (engineStatus !== "ready") {
      return;
    }
    let cancelled = false;
    void client.status().then((next) => {
      if (!cancelled) {
        setStatus(next);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, engineStatus]);

  if (engineStatus === "incompatible") {
    return (
      <section className="updates-page">
        <p className="page-kicker">Updates</p>
        <h1 className="page-title">Updates</h1>
        <p className="page-body">
          Incompatible engine version. Upgrade or rollback is refused until desktop and engine
          share a compatible major version.
        </p>
      </section>
    );
  }

  if (engineStatus !== "ready") {
    return (
      <section className="updates-page">
        <p className="page-kicker">Updates</p>
        <h1 className="page-title">Updates</h1>
        <p className="page-body">
          Connect a compatible engine to inspect updates, checksums, SBOM, and provenance.
        </p>
      </section>
    );
  }

  return (
    <section className="updates-page">
      <p className="page-kicker">Updates</p>
      <h1 className="page-title">Updates</h1>
      <p className="page-body">
        Engine {status?.engineVersion ?? "0.2.0"}. Desktop {status?.clientVersion ?? "0.2.0"}.
      </p>
      <p className="workspace-card__meta">
        {status?.signed ? "Signed" : "Not signed"}. Checksums{" "}
        {status?.checksumsPresent ? "present" : "missing"}. SBOM{" "}
        {status?.sbomPresent ? "present" : "missing"}.
      </p>
      <button
        type="button"
        className="btn-quiet"
        onClick={() => {
          void client.rollback().then((next) => {
            setRolled(next.version);
          });
        }}
      >
        Rollback
      </button>
      {rolled ? <p className="workspace-card__meta">Rolled back to {rolled}.</p> : null}
    </section>
  );
}
