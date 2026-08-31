// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionSettingsClient,
  type OpsSettingsView,
  type SettingsPageClients,
} from "./client";

export type { SettingsPageClients } from "./client";

interface SettingsPageProps {
  engineClient: EngineClient;
  settingsClient?: SettingsPageClients;
}

const productionSettings = createProductionSettingsClient();

export function SettingsPage({ engineClient, settingsClient }: SettingsPageProps) {
  const client = settingsClient ?? productionSettings;
  const [ready, setReady] = useState(false);
  const [settings, setSettings] = useState<OpsSettingsView>({
    otelExport: false,
    langfuseExport: false,
  });
  const [findings, setFindings] = useState<string[]>([]);
  const [backupPath, setBackupPath] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engineClient.getState().then((state) => {
        if (!cancelled) {
          setReady(state.status === "ready");
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
    if (!ready) {
      return;
    }
    let cancelled = false;
    void client.load().then((next) => {
      if (!cancelled) {
        setSettings(next);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="settings-page">
        <p className="page-kicker">Settings</p>
        <h1 className="page-title">Settings</h1>
        <p className="page-body">
          Connect a compatible engine to change settings. Tokens and private keys are never pasted
          here.
        </p>
      </section>
    );
  }

  async function onToggleOtel() {
    const next = { ...settings, otelExport: !settings.otelExport };
    const saved = await client.save(next);
    setSettings(saved);
  }

  async function onDoctor() {
    const report = await client.doctor();
    setFindings(report.findings);
  }

  async function onBackup() {
    const archive = await client.backup();
    setBackupPath(archive.path);
  }

  return (
    <section className="settings-page">
      <p className="page-kicker">Settings</p>
      <h1 className="page-title">Settings</h1>
      <p className="page-body">
        Export is off by default. GitHub PEMs and Telegram bot tokens stay in the OS secret store
        and the Connections native import flow.
      </p>
      <label className="models__confirm">
        <input
          type="checkbox"
          checked={settings.otelExport}
          onChange={() => {
            void onToggleOtel();
          }}
        />
        OpenTelemetry export
      </label>
      <div className="workspaces__toolbar">
        <button type="button" className="btn-quiet" onClick={() => void onDoctor()}>
          Run doctor
        </button>
        <button type="button" className="btn-quiet" onClick={() => void onBackup()}>
          Backup
        </button>
      </div>
      {findings.length > 0 ? (
        <ul className="dashboard-list">
          {findings.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      {backupPath ? <p className="workspace-card__meta">{backupPath}</p> : null}
    </section>
  );
}
