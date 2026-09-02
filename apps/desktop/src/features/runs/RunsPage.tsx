// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import { createProductionRunsClient, type RunRecord, type RunsClient } from "./client";

export type { RunsClient } from "./client";

interface RunsPageProps {
  engineClient: EngineClient;
  runsClient?: RunsClient;
  goalId?: string;
}

const productionRuns = createProductionRunsClient();

export function RunsPage({ engineClient, runsClient, goalId }: RunsPageProps) {
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
    let after = 0;
    const refresh = () => {
      void Promise.all([client.list(), client.pollEvents(after)])
        .then(([items, streamed]) => {
          if (!cancelled) {
            setRuns(items);
            after = streamed.headSeq;
          }
        })
        .catch(() => {
          if (!cancelled) {
            setError("Could not load runs.");
          }
        });
    };
    refresh();
    const interval = window.setInterval(refresh, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="runs-page">
        <p className="page-kicker">Runs</p>
        <h1 className="page-title">Runs</h1>
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  const visibleRuns = goalId ? runs.filter((run) => run.goalId === goalId) : runs;

  return (
    <section className="runs-page">
      <p className="page-kicker">Runs</p>
      <h1 className="page-title">Runs</h1>
      <p className="page-body">
        Each run records artifacts, budgets, and PR links. Failures stay explainable and never
        merge without a reproduction test.
      </p>
      {visibleRuns.length ? (
        <ul className="runs-page__list">
          {visibleRuns.map((run) => (
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
