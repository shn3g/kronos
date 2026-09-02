// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import { DESKTOP_CLIENT_VERSION } from "../../api/kronosClient";
import type { EngineClient } from "../../engine/client";
import {
  createProductionUpdatesClient,
  type UpdateStatusView,
  type UpdatesPageClients,
} from "./client";
import type { UpdateCheckResult } from "./appUpdater";

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
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [updateCheck, setUpdateCheck] = useState<UpdateCheckResult | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const signingConfigured = client.updaterSigningConfigured();

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
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  return (
    <section className="updates-page">
      <p className="page-kicker">Updates</p>
      <h1 className="page-title">Updates</h1>
      <p className="page-body">
        Engine {status?.engineVersion ?? DESKTOP_CLIENT_VERSION}. Desktop{" "}
        {status?.clientVersion ?? DESKTOP_CLIENT_VERSION}.
      </p>
      <p className="workspace-card__meta">
        Release artifacts {status?.signed ? "signed" : "not signed"}. Checksums{" "}
        {status?.checksumsPresent ? "present" : "missing"}. SBOM{" "}
        {status?.sbomPresent ? "present" : "missing"}. Provenance{" "}
        {status?.provenancePresent ? "present" : "missing"}.
      </p>
      <p className="workspace-card__meta">
        Installers are not code-signed for SmartScreen or Gatekeeper. Windows may show SmartScreen
        and macOS may show Gatekeeper until a publisher certificate is added.
      </p>
      {!signingConfigured ? (
        <p className="page-body" role="status">
          Updates are not signed yet.
        </p>
      ) : null}
      <button
        type="button"
        className="btn-quiet"
        disabled={!signingConfigured || checking}
        onClick={() => {
          setInstallError(null);
          setChecking(true);
          void client
            .checkForUpdates()
            .then((result) => {
              setUpdateCheck(result);
            })
            .catch((error: unknown) => {
              const message = error instanceof Error ? error.message : "Update check failed.";
              setInstallError(message);
            })
            .finally(() => {
              setChecking(false);
            });
        }}
      >
        {checking ? "Checking for updates…" : "Check for updates"}
      </button>
      {updateCheck?.status === "up-to-date" ? (
        <p className="workspace-card__meta" role="status">
          You are on the latest version ({updateCheck.currentVersion}).
        </p>
      ) : null}
      {updateCheck?.status === "available" ? (
        <div className="updates-available">
          <p className="page-body" role="status">
            {updateCheck.version} is available.
          </p>
          <p className="workspace-card__meta">{updateCheck.notes}</p>
          <button
            type="button"
            className="btn-quiet"
            disabled={installing}
            onClick={() => {
              setInstallError(null);
              setInstalling(true);
              void client
                .installAndRestart()
                .catch((error: unknown) => {
                  const message = error instanceof Error ? error.message : "Install failed.";
                  setInstallError(message);
                })
                .finally(() => {
                  setInstalling(false);
                });
            }}
          >
            {installing ? "Installing…" : "Install and restart"}
          </button>
        </div>
      ) : null}
      {installError ? (
        <p className="workspace-card__meta" role="alert">
          {installError}
        </p>
      ) : null}
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
