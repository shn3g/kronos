// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionModelsClient,
  type ModelRole,
  type ModelsClient,
  type ModelsSnapshot,
} from "./client";

export type { ModelsClient } from "./client";

const productionModels = createProductionModelsClient();
const ROLES: ModelRole[] = ["planner", "coder", "reviewer", "embedding"];

interface ModelsPageProps {
  engineClient: EngineClient;
  modelsClient?: ModelsClient;
}

export function ModelsPage({ engineClient, modelsClient }: ModelsPageProps) {
  const client = modelsClient ?? productionModels;
  const [ready, setReady] = useState(false);
  const [snapshot, setSnapshot] = useState<ModelsSnapshot | null>(null);
  const [assignments, setAssignments] = useState<Record<ModelRole, string>>({
    planner: "",
    coder: "",
    reviewer: "",
    embedding: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

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
    void client.snapshot().then((next) => {
      if (cancelled) {
        return;
      }
      setSnapshot(next);
      setAssignments({
        planner: next.assignments.planner ?? "",
        coder: next.assignments.coder ?? "",
        reviewer: next.assignments.reviewer ?? "",
        embedding: next.assignments.embedding ?? "",
      });
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="models">
        <p className="page-kicker">Models</p>
        <h1 className="page-title">Models</h1>
        <p className="page-body">
          Connect a compatible engine to assign model profiles. Routing stays closed until the
          local engine is ready.
        </p>
      </section>
    );
  }

  async function onSave() {
    setError(null);
    setSaved(false);
    try {
      const next = await client.assign(assignments);
      setAssignments({
        planner: next.planner ?? "",
        coder: next.coder ?? "",
        reviewer: next.reviewer ?? "",
        embedding: next.embedding ?? "",
      });
      setSaved(true);
    } catch {
      setError("Could not save model assignments.");
    }
  }

  return (
    <section className="models">
      <p className="page-kicker">Models</p>
      <h1 className="page-title">Models</h1>
      <p className="page-body">
        Assign explicit planner, coder, reviewer, and embedding profiles. Kronos never silently
        falls back to an unapproved or paid model.
      </p>
      {snapshot?.detected.length ? (
        <ul className="models__detected">
          {snapshot.detected.map((tool) => (
            <li key={`${tool.kind}:${tool.label}`}>{tool.label}</li>
          ))}
        </ul>
      ) : null}
      <form
        className="models__form"
        onSubmit={(event) => {
          event.preventDefault();
          void onSave();
        }}
      >
        {ROLES.map((role) => (
          <label key={role} className="models__field" htmlFor={`model-${role}`}>
            {`${role.charAt(0).toUpperCase()}${role.slice(1)}`}
            <select
              id={`model-${role}`}
              value={assignments[role]}
              onChange={(event) => {
                setSaved(false);
                setAssignments((current) => ({ ...current, [role]: event.target.value }));
              }}
            >
              <option value="">Select a profile</option>
              {(snapshot?.profiles ?? []).map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.displayName}
                  {profile.billed ? " (paid)" : ""}
                </option>
              ))}
            </select>
          </label>
        ))}
        <button type="submit" className="btn-primary">
          Save assignments
        </button>
      </form>
      {saved ? <p className="models__saved">Assignments saved.</p> : null}
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}
