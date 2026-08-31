// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useMemo, useState } from "react";
import type { EngineClient } from "../../engine/client";
import { createProductionHomeClient, type HomeClient, type HomeDashboard } from "./client";

export type { HomeClient, HomeDashboard } from "./client";

export interface HomePageClients extends HomeClient {}

interface HomePageProps {
  engineClient: EngineClient;
  homeClient?: HomePageClients;
}

const productionHome = createProductionHomeClient();

export function HomePage({ engineClient, homeClient }: HomePageProps) {
  const client = homeClient ?? productionHome;
  const [ready, setReady] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [dash, setDash] = useState<HomeDashboard | null>(null);

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
    void client.dashboard().then((next) => {
      if (cancelled) {
        return;
      }
      setDash(next);
      setSelectedId((current) => current || next.repositories[0]?.id || "");
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  const filtered = useMemo(() => {
    if (!dash) {
      return null;
    }
    if (!selectedId) {
      return dash;
    }
    const matchesRepo = (item: { repositoryId?: string }) => item.repositoryId === selectedId;
    return {
      ...dash,
      schedules: dash.schedules.filter(matchesRepo),
      budgets: dash.budgets.filter((item) => item.repositoryId === selectedId),
      runs: dash.runs.filter(matchesRepo),
      diffs: dash.diffs.filter(matchesRepo),
      tests: dash.tests.filter(matchesRepo),
      index: dash.index.filter((item) => item.repositoryId === selectedId),
    };
  }, [dash, selectedId]);

  if (!ready) {
    return (
      <section className="home-page">
        <p className="page-kicker">Home</p>
        <h1 className="page-title">Home</h1>
        <p className="page-body">
          Connect a compatible engine to open the dashboard. Schedules, budgets, and index health
          stay closed until the local engine is ready.
        </p>
      </section>
    );
  }

  return (
    <section className="home-page">
      <p className="page-kicker">Home</p>
      <h1 className="page-title">Home</h1>
      <p className="page-body">
        One installation, many isolated repositories. Switch the active repository to inspect
        schedules, budgets, runs, diffs, tests, and index health.
      </p>
      <label className="wizard__label" htmlFor="home-repo">
        Repository
        <select
          id="home-repo"
          className="wizard__input"
          value={selectedId}
          onChange={(event) => {
            setSelectedId(event.target.value);
          }}
        >
          {(filtered?.repositories ?? dash?.repositories ?? []).map((repo) => (
            <option key={repo.id} value={repo.id}>
              {repo.displayName}
            </option>
          ))}
        </select>
      </label>
      <div className="dashboard-grid">
        <article className="workspace-card">
          <h2 className="workspace-card__name">Schedules</h2>
          <ul className="dashboard-list">
            {(filtered?.schedules ?? []).map((item) => (
              <li key={item.id}>
                {item.title}
                <span className="workspace-card__meta"> {item.schedule}</span>
              </li>
            ))}
          </ul>
        </article>
        <article className="workspace-card">
          <h2 className="workspace-card__name">Budgets</h2>
          {(filtered?.budgets ?? []).map((item) => (
            <p key={item.repositoryId} className="workspace-card__meta">
              {item.dailyDispatches} dispatches. Breaker {item.breakerOpen ? "open" : "closed"}.
            </p>
          ))}
          {(filtered?.budgets ?? []).length === 0 ? (
            <p className="workspace-card__meta">Breaker closed. No meter yet.</p>
          ) : null}
        </article>
        <article className="workspace-card">
          <h2 className="workspace-card__name">Runs</h2>
          {(filtered?.runs ?? []).map((item) => (
            <p key={item.id} className="workspace-card__meta">
              {item.status}: {item.evidence}
            </p>
          ))}
        </article>
        <article className="workspace-card">
          <h2 className="workspace-card__name">Diffs</h2>
          {(filtered?.diffs ?? []).map((item) => (
            <p key={item.path} className="workspace-card__meta">
              {item.path} {item.summary}
            </p>
          ))}
        </article>
        <article className="workspace-card">
          <h2 className="workspace-card__name">Tests</h2>
          {(filtered?.tests ?? []).map((item) => (
            <p key={item.name} className="workspace-card__meta">
              {item.name} {item.passed ? "passed" : "failed"}
            </p>
          ))}
        </article>
        <article className="workspace-card">
          <h2 className="workspace-card__name">Index health</h2>
          {(filtered?.index ?? []).map((item) => (
            <p key={item.repositoryId} className="workspace-card__meta">
              {item.ready ? "ready" : "not ready"} · {item.chunkCount} chunks · dense{" "}
              {item.denseAvailable ? "on" : "off"}
            </p>
          ))}
        </article>
      </div>
    </section>
  );
}
