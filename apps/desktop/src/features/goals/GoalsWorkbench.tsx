// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import { RunsPage } from "../runs/RunsPage";
import { createProductionRunsClient, type RunsClient } from "../runs/client";
import {
  createProductionRepositoriesClient,
  type EnrolledRepository,
  type RepositoriesClient,
} from "../workspaces/client";
import {
  createProductionGoalsClient,
  type GoalDraft,
  type GoalReadinessResult,
  type GoalRecord,
  type GoalTask,
  type GoalsClient,
} from "./client";
import { GoalCreateWizard } from "./GoalCreateWizard";
import { readinessFixHref } from "./readinessFixHref";

export type { GoalsClient } from "./client";

export interface GoalsWorkbenchClients extends GoalsClient {
  listRepositories(): Promise<EnrolledRepository[]>;
}

interface GoalsWorkbenchProps {
  engineClient: EngineClient;
  /** When the shell already knows the engine is ready, skip the waiting flash on mount. */
  engineReady?: boolean;
  goalsClient?: GoalsWorkbenchClients;
  repositoriesClient?: RepositoriesClient;
  runsClient?: RunsClient;
  selectedGoalReveal?: { id: string; nonce: number };
}

const productionGoals = createProductionGoalsClient();
const productionRepos = createProductionRepositoriesClient();
const productionRuns = createProductionRunsClient();
const productionWorkbenchClient: GoalsWorkbenchClients = {
  ...productionGoals,
  listRepositories: () => productionRepos.list(),
};

export function GoalsWorkbench({
  engineClient,
  engineReady = false,
  goalsClient,
  repositoriesClient,
  runsClient,
  selectedGoalReveal,
}: GoalsWorkbenchProps) {
  const client = goalsClient ?? productionWorkbenchClient;
  const repos = repositoriesClient ?? productionRepos;
  const runs = runsClient ?? productionRuns;
  const [ready, setReady] = useState(engineReady);
  const [goals, setGoals] = useState<GoalRecord[]>([]);
  const [repositories, setRepositories] = useState<EnrolledRepository[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [tasks, setTasks] = useState<GoalTask[]>([]);
  const [readiness, setReadiness] = useState<GoalReadinessResult | null>(null);
  const [autonomyMode, setAutonomyMode] = useState<string | null>(null);
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
    if (engineReady) {
      setReady(true);
    }
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
  }, [engineClient, engineReady]);

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
      ]).then(([items, reposList, streamed]) => {
        if (cancelled) {
          return;
        }
        setGoals(items);
        setRepositories(reposList);
        after = streamed.headSeq;
        setDraft((current) => ({
          ...current,
          repositoryId: current.repositoryId || reposList[0]?.id || "",
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

  useEffect(() => {
    if (!selectedGoalReveal?.id) {
      return;
    }
    setSelectedId(selectedGoalReveal.id);
  }, [selectedGoalReveal?.id, selectedGoalReveal?.nonce]);

  useEffect(() => {
    if (!ready || selectedId === "") {
      setTasks([]);
      setReadiness(null);
      setAutonomyMode(null);
      return;
    }
    let cancelled = false;
    setTasks([]);
    setReadiness(null);
    setAutonomyMode(null);
    setError(null);
    const load = async () => {
      try {
        const detail = await client.get(selectedId);
        if (cancelled) {
          return;
        }
        setTasks(detail.tasks);
        const goal = detail.goal;
        if (goal.repositoryId) {
          const [readinessResult, repoDetail] = await Promise.all([
            client.goalReadiness(goal.repositoryId),
            repos.get(goal.repositoryId),
          ]);
          if (!cancelled) {
            setReadiness(readinessResult);
            const mode = repoDetail.policy.autonomy.mode;
            const frozen = repoDetail.policy.autonomy.freeze;
            setAutonomyMode(frozen ? `${mode} (frozen)` : mode);
          }
        }
      } catch {
        if (!cancelled) {
          setError("Could not load goal details.");
          setTasks([]);
          setReadiness(null);
          setAutonomyMode(null);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [client, ready, repos, selectedId]);

  if (!ready) {
    return (
      <section className="goals-workbench">
        <p className="page-kicker">Goals</p>
        <h1 className="page-title">Goals</h1>
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  async function onCreate() {
    setError(null);
    try {
      const created = await client.create(draft);
      const planned = await client.plan(created.id);
      setGoals((current) => [planned.goal, ...current]);
      setSelectedId(planned.goal.id);
      setTasks(planned.tasks);
    } catch {
      setError("Could not create the goal.");
    }
  }

  async function onSelect(id: string) {
    setSelectedId(id);
  }

  async function onPlan() {
    if (!selectedId) {
      return;
    }
    setError(null);
    try {
      const planned = await client.plan(selectedId);
      setGoals((current) =>
        current.map((item) => (item.id === selectedId ? planned.goal : item)),
      );
      setTasks(planned.tasks);
    } catch {
      setError("Could not plan the goal.");
    }
  }

  async function onTick() {
    setError(null);
    try {
      await client.tick();
    } catch {
      setError("Could not tick the goal engine.");
    }
  }

  const selected = goals.find((item) => item.id === selectedId) ?? null;

  return (
    <section className="goals-workbench">
      <p className="page-kicker">Goals</p>
      <h1 className="page-title">Goals</h1>
      <p className="page-body">Create bounded goals and review readiness before unattended work.</p>
      <GoalCreateWizard
        draft={draft}
        repositories={repositories}
        onDraftChange={setDraft}
        onSubmit={() => {
          void onCreate();
        }}
      />
      <div className="goals-workbench__layout">
        <aside className="goals-workbench__list" aria-label="Goals list">
          {goals.length ? (
            <ul className="goals-page__list">
              {goals.map((goal) => (
                <li key={goal.id}>
                  <button
                    type="button"
                    className="workspace-card"
                    aria-current={goal.id === selectedId ? "true" : undefined}
                    onClick={() => {
                      void onSelect(goal.id);
                    }}
                  >
                    <p className="workspace-card__name">{goal.title}</p>
                    <p className="workspace-card__meta">
                      <span className="goals-workbench__state">{goal.state}</span>
                      {" · "}
                      {goal.source} · risk {goal.riskCeiling}
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
        </aside>
        <div className="goals-workbench__detail">
          {selected ? (
            <>
              <div className="wizard">
                <h2 className="wizard__title">{selected.title}</h2>
                <p className="wizard__copy">{selected.successCriteria}</p>
                <p className="wizard__copy">Non-goals: {selected.nonGoals}</p>
                <div className="goals-workbench__actions">
                  <button type="button" className="btn-primary" onClick={() => void onPlan()}>
                    Plan
                  </button>
                  <button type="button" className="btn-quiet" onClick={() => void onTick()}>
                    Tick
                  </button>
                </div>
                {autonomyMode ? (
                  <p className="wizard__copy">
                    Autonomy mode: <strong>{autonomyMode}</strong>. This comes from the committed
                    workspace policy and cannot be changed here.
                  </p>
                ) : null}
                <h3 className="wizard__title">Plan steps</h3>
                {tasks.length ? (
                  tasks.map((task) => (
                    <p key={task.id} className="workspace-card__meta">
                      {task.title} · {task.state}
                      {task.prUrl ? ` · ${task.prUrl}` : ""}
                      {task.stopReason ? ` · ${task.stopReason}` : ""}
                    </p>
                  ))
                ) : (
                  <p className="wizard__copy">No plan steps yet. Use Plan to generate tasks.</p>
                )}
              </div>
              <ReadinessPanel readiness={readiness} repositoryId={selected.repositoryId} />
            </>
          ) : (
            <p className="index-page__empty">Select a goal to see its plan and readiness.</p>
          )}
        </div>
      </div>
      <RunsPage
        engineClient={engineClient}
        engineReady={ready}
        runsClient={runs}
        {...(selected ? { goalId: selected.id } : {})}
      />
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}

function ReadinessPanel({
  readiness,
  repositoryId,
}: {
  readiness: GoalReadinessResult | null;
  repositoryId: string;
}) {
  if (!repositoryId) {
    return (
      <section className="goals-workbench__readiness" aria-label="Goal readiness">
        <h3 className="wizard__title">Readiness</h3>
        <p className="wizard__copy">No repository is linked to this goal yet.</p>
      </section>
    );
  }
  if (!readiness) {
    return (
      <section className="goals-workbench__readiness" aria-label="Goal readiness">
        <h3 className="wizard__title">Readiness</h3>
        <p className="wizard__copy">Loading readiness checks…</p>
      </section>
    );
  }
  return (
    <section className="goals-workbench__readiness" aria-label="Goal readiness">
      <h3 className="wizard__title">Readiness</h3>
      <p className="wizard__copy">
        Status: {readiness.canExecute ? "ready" : "needs attention"}
      </p>
      <ul className="health-list">
        {readiness.checks.map((check) => (
          <li key={check.id} className="health-list__item" data-ok={check.ok ? "true" : "false"}>
            <span className="health-list__mark" aria-hidden="true">
              {check.ok ? "✓" : "!"}
            </span>
            <span>
              <strong>
                {check.label}
                <span className="health-list__state">
                  {check.ok ? "ready" : "needs attention"}
                </span>
              </strong>
              <span className="health-list__detail">{check.detail}</span>
              {!check.ok ? (
                <ReadinessFixLink check={check} />
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ReadinessFixLink({ check }: { check: { id: string; label: string } }) {
  const href = readinessFixHref(check.id);
  if (!href) {
    return null;
  }
  return (
    <a className="goals-workbench__fix-link" href={href}>
      Fix {check.label}
    </a>
  );
}
