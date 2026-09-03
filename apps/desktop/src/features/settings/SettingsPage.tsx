// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import { useEngineConnection } from "../../engine/EngineConnectionProvider";
import {
  createProductionSettingsClient,
  type OpsSettingsView,
  type SettingsPageClients,
} from "./client";

export type { SettingsPageClients } from "./client";

interface SettingsPageProps {
  settingsClient?: SettingsPageClients;
}

const productionSettings = createProductionSettingsClient();

export function SettingsPage({ settingsClient }: SettingsPageProps) {
  const client = settingsClient ?? productionSettings;
  const { engineReady: ready } = useEngineConnection();
  const [settings, setSettings] = useState<OpsSettingsView>({
    otelExport: false,
    langfuseExport: false,
  });
  const [findings, setFindings] = useState<string[]>([]);
  const [backupPath, setBackupPath] = useState<string | null>(null);

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
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  async function onToggleOtel() {
    const next = { ...settings, otelExport: !settings.otelExport };
    const saved = await client.save(next);
    setSettings(saved);
  }

  async function onToggleLangfuse() {
    const next = { ...settings, langfuseExport: !settings.langfuseExport };
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
        Telemetry, backups, and doctor checks for this install. Tokens and keys stay in the OS
        secret store.
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
      <label className="models__confirm">
        <input
          type="checkbox"
          checked={settings.langfuseExport}
          onChange={() => {
            void onToggleLangfuse();
          }}
        />
        Langfuse export
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
