// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionMemoryClient,
  type MemoryClient,
  type MemoryRecord,
} from "./client";

export type { MemoryClient } from "./client";

interface MemoryPageProps {
  engineClient: EngineClient;
  memoryClient?: MemoryClient;
}

const productionMemory = createProductionMemoryClient();

export function MemoryPage({ engineClient, memoryClient }: MemoryPageProps) {
  const client = memoryClient ?? productionMemory;
  const [ready, setReady] = useState(false);
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [yaml, setYaml] = useState("");
  const [error, setError] = useState<string | null>(null);

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
    void client.list().then((items) => {
      if (!cancelled) {
        setRecords(items);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="memory-page">
        <p className="page-kicker">Memory</p>
        <h1 className="page-title">Memory</h1>
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  async function onImport() {
    setError(null);
    try {
      await client.importLessons(yaml);
      setYaml("");
      setRecords(await client.list());
    } catch {
      setError("Could not import lessons.");
    }
  }

  return (
    <section className="memory-page">
      <p className="page-kicker">Memory</p>
      <h1 className="page-title">Memory</h1>
      <p className="page-body">
        Records stay human-readable with source SHAs, outcomes, and confidence. Imported lessons
        arrive as disabled candidates. Propose is not activate.
      </p>
      <label className="index-page__field">
        Lesson YAML
        <textarea
          className="wizard__input"
          value={yaml}
          onChange={(event) => setYaml(event.target.value)}
        />
      </label>
      <button type="button" className="btn-primary" onClick={() => void onImport()}>
        Import as disabled candidates
      </button>
      {error ? <p className="wizard__error">{error}</p> : null}
      {records.length ? (
        <ul className="memory-page__list">
          {records.map((record) => (
            <li key={record.id} className="workspace-card">
              <p className="workspace-card__name">
                {record.id} · {record.status}
              </p>
              <p className="workspace-card__meta">
                {record.kind} · SHA {record.sourceSha.slice(0, 12)} · helpful {record.helpful} ·
                harmful {record.harmful} · confidence {record.confidence}
              </p>
              <p className="workspace-card__status">{record.text}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="page-body">No memory records yet.</p>
      )}
    </section>
  );
}
