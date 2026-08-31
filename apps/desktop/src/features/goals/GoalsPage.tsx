// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionRepositoriesClient,
  type EnrolledRepository,
} from "../workspaces/client";
import {
  createProductionGoalsClient,
  type GoalDraft,
  type GoalRecord,
  type GoalTask,
  type GoalsClient,
} from "./client";

export type { GoalsClient } from "./client";

export interface GoalsPageClients extends GoalsClient {
  listRepositories(): Promise<EnrolledRepository[]>;
}

interface GoalsPageProps {
  engineClient: EngineClient;
  goalsClient?: GoalsPageClients;
}

const productionGoals = createProductionGoalsClient();
const productionRepos = createProductionRepositoriesClient();
const productionPageClient: GoalsPageClients = {
  ...productionGoals,
  listRepositories: () => productionRepos.list(),
};

export function GoalsPage({ engineClient, goalsClient }: GoalsPageProps) {
  const client = goalsClient ?? productionPageClient;
  const [ready, setReady] = useState(false);
  const [goals, setGoals] = useState<GoalRecord[]>([]);
  const [repositories, setRepositories] = useState<EnrolledRepository[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [tasks, setTasks] = useState<GoalTask[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<GoalDraft>({
    repositoryId: "",
    title: "",
    successCriteria: "",
    nonGoals: "",
    riskCeiling: "low",
    source: "desktop",
    maxAttempts: 3,
  });

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
      void Promise.all([
        client.list(),
        client.listRepositories(),
        client.pollEvents(after),
        client.tick(),
      ]).then(([items, repos, streamed]) => {
        if (cancelled) {
          return;
        }
        setGoals(items);
        setRepositories(repos);
        after = streamed.headSeq;
        setDraft((current) => ({
          ...current,
          repositoryId: current.repositoryId || repos[0]?.id || "",
        }));
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
      <section className="goals-page">
        <p className="page-kicker">Goals</p>
        <h1 className="page-title">Goals</h1>
        <p className="page-body">
          Connect a compatible engine to create and track bounded goals. Planning stays closed
          until the local engine is ready.
        </p>
      </section>
    );
  }

  async function onCreate() {
    setError(null);
    try {
      const created = await client.create(draft);
      const planned = await client.plan(created.id);
      setGoals((current) => [planned.goal, ...current]);
    } catch {
      setError("Could not create the goal.");
    }
  }

  async function onSelect(id: string) {
    setSelectedId(id);
    setError(null);
    try {
      const detail = await client.get(id);
      setTasks(detail.tasks);
    } catch {
      setError("Could not load goal tasks.");
    }
  }

  const selected = goals.find((item) => item.id === selectedId) ?? null;

  return (
    <section className="goals-page">
      <p className="page-kicker">Goals</p>
      <h1 className="page-title">Goals</h1>
      <p className="page-body">
        Bounded goals require a repository, success criteria, non-goals, budget, and a risk
        ceiling. Tasks, failures, and PR links appear after planning.
      </p>
      <form
        className="wizard"
        onSubmit={(event) => {
          event.preventDefault();
          void onCreate();
        }}
      >
        <h2 className="wizard__title">Create goal</h2>
        <label className="wizard__label" htmlFor="goal-repo">
          Repository
          <select
            id="goal-repo"
            className="wizard__input"
            value={draft.repositoryId}
            onChange={(event) => {
              setDraft({ ...draft, repositoryId: event.target.value });
            }}
          >
            {repositories.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.displayName}
              </option>
            ))}
          </select>
        </label>
        <label className="wizard__label" htmlFor="goal-title">
          Title
          <input
            id="goal-title"
            className="wizard__input"
            value={draft.title}
            onChange={(event) => {
              setDraft({ ...draft, title: event.target.value });
            }}
          />
        </label>
        <label className="wizard__label" htmlFor="goal-criteria">
          Success criteria
          <textarea
            id="goal-criteria"
            className="wizard__input"
            value={draft.successCriteria}
            onChange={(event) => {
              setDraft({ ...draft, successCriteria: event.target.value });
            }}
          />
        </label>
        <label className="wizard__label" htmlFor="goal-nongoals">
          Non-goals
          <textarea
            id="goal-nongoals"
            className="wizard__input"
            value={draft.nonGoals}
            onChange={(event) => {
              setDraft({ ...draft, nonGoals: event.target.value });
            }}
          />
        </label>
        <label className="wizard__label" htmlFor="goal-risk">
          Risk ceiling
          <select
            id="goal-risk"
            className="wizard__input"
            value={draft.riskCeiling}
            onChange={(event) => {
              setDraft({ ...draft, riskCeiling: event.target.value });
            }}
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
        </label>
        <label className="wizard__label" htmlFor="goal-budget">
          Attempt budget
          <input
            id="goal-budget"
            className="wizard__input"
            type="number"
            min={1}
            value={draft.maxAttempts}
            onChange={(event) => {
              setDraft({ ...draft, maxAttempts: Number(event.target.value) });
            }}
          />
        </label>
        <button type="submit" className="btn-primary">
          Create goal
        </button>
      </form>
      {goals.length ? (
        <ul className="goals-page__list">
          {goals.map((goal) => (
            <li key={goal.id}>
              <button type="button" className="workspace-card" onClick={() => void onSelect(goal.id)}>
                <p className="workspace-card__name">{goal.title}</p>
                <p className="workspace-card__meta">
                  {goal.state} · {goal.source} · risk {goal.riskCeiling}
                </p>
                {goal.stopReason ? (
                  <p className="workspace-card__status">{goal.stopReason}</p>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="index-page__empty">No goals yet.</p>
      )}
      {selected ? (
        <div className="wizard">
          <h2 className="wizard__title">{selected.title}</h2>
          <p className="wizard__copy">{selected.successCriteria}</p>
          <p className="wizard__copy">Non-goals: {selected.nonGoals}</p>
          {tasks.map((task) => (
            <p key={task.id} className="workspace-card__meta">
              {task.title} · {task.state}
              {task.prUrl ? ` · ${task.prUrl}` : ""}
              {task.stopReason ? ` · ${task.stopReason}` : ""}
            </p>
          ))}
        </div>
      ) : null}
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}
