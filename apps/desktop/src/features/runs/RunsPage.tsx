// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import { createProductionRunsClient, type RunRecord, type RunsClient } from "./client";

export type { RunsClient } from "./client";

interface RunsPageProps {
  engineClient: EngineClient;
  runsClient?: RunsClient;
}

const productionRuns = createProductionRunsClient();

export function RunsPage({ engineClient, runsClient }: RunsPageProps) {
  const client = runsClient ?? productionRuns;
  const [ready, setReady] = useState(false);
  const [runs, setRuns] = useState<RunRecord[]>([]);
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
    void client
      .list()
      .then((items) => {
        if (!cancelled) {
          setRuns(items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not load runs.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="runs-page">
        <p className="page-kicker">Runs</p>
        <h1 className="page-title">Runs</h1>
        <p className="page-body">
          Connect a compatible engine to inspect task runs, tests, and review evidence. This
          screen stays closed until the local engine is ready.
        </p>
      </section>
    );
  }

  return (
    <section className="runs-page">
      <p className="page-kicker">Runs</p>
      <h1 className="page-title">Runs</h1>
      <p className="page-body">
        Each run records artifacts, budgets, and PR links. Failures stay explainable and never
        merge without a reproduction test.
      </p>
      {runs.length ? (
        <ul className="runs-page__list">
          {runs.map((run) => (
            <li key={run.id} className="workspace-card">
              <p className="workspace-card__name">
                {run.taskId} · {run.status}
              </p>
              <p className="workspace-card__meta">{run.evidence}</p>
              {run.prUrl ? <p className="workspace-card__status">{run.prUrl}</p> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="index-page__empty">No runs yet.</p>
      )}
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}
