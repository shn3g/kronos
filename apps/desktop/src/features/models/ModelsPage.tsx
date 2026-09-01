// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionModelsClient,
  type DetectedTool,
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
  headingLevel?: "h1" | "h2";
}

export function ModelsPage({ engineClient, modelsClient, headingLevel = "h1" }: ModelsPageProps) {
  const client = modelsClient ?? productionModels;
  const [ready, setReady] = useState(false);
  const [snapshot, setSnapshot] = useState<ModelsSnapshot | null>(null);
  const [assignments, setAssignments] = useState<Record<ModelRole, string>>({
    planner: "",
    coder: "",
    reviewer: "",
    embedding: "",
  });
  const [confirmShared, setConfirmShared] = useState(false);
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
      setAssignments(assignmentsFromSnapshot(next));
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  const Title = headingLevel === "h2" ? "h2" : "h1";
  const titleClass = headingLevel === "h2" ? "section-title" : "page-title";

  if (!ready) {
    return (
      <section className="models">
        <Title className={titleClass}>Models</Title>
        <p className="page-body">
          Connect a compatible engine to assign model profiles. Routing stays closed until the
          local engine is ready.
        </p>
      </section>
    );
  }

  async function onRegister(tool: DetectedTool) {
    setError(null);
    setSaved(false);
    try {
      const created = await client.createProvider({
        kind: tool.kind,
        displayName: tool.label,
        baseUrl: tool.kind === "openai_compatible" ? tool.label : null,
        billed: false,
      });
      const next: ModelsSnapshot = {
        detected: snapshot?.detected ?? [tool],
        profiles: created.profiles,
        assignments: snapshot?.assignments ?? {
          planner: null,
          coder: null,
          reviewer: null,
          embedding: null,
        },
      };
      setSnapshot(next);
      setAssignments(assignmentsFromProfiles(created.profiles));
    } catch {
      setError("Could not register the detected provider.");
    }
  }

  async function onSave() {
    setError(null);
    setSaved(false);
    try {
      const next = confirmShared
        ? await client.assign(assignments, { confirmSharedRoles: true })
        : await client.assign(assignments);
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
      <Title className={titleClass}>Models</Title>
      <p className="page-body">
        Assign explicit planner, coder, reviewer, and embedding profiles. Kronos never silently
        falls back to an unapproved or paid model.
      </p>
      {snapshot?.detected.length ? (
        <ul className="models__detected">
          {snapshot.detected.map((tool) => (
            <li key={`${tool.kind}:${tool.label}`}>
              <span>{tool.label}</span>
              {snapshot.profiles.length === 0 ? (
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => {
                    void onRegister(tool);
                  }}
                >
                  Register as provider
                </button>
              ) : null}
            </li>
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
        <label className="models__confirm" htmlFor="model-confirm-shared">
          <input
            id="model-confirm-shared"
            type="checkbox"
            checked={confirmShared}
            onChange={(event) => {
              setConfirmShared(event.target.checked);
            }}
          />
          Use one local model for all four roles
        </label>
        <button type="submit" className="btn-primary">
          Save assignments
        </button>
      </form>
      {saved ? <p className="models__saved">Assignments saved.</p> : null}
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}

function assignmentsFromSnapshot(snapshot: ModelsSnapshot): Record<ModelRole, string> {
  const fromSaved: Record<ModelRole, string> = {
    planner: snapshot.assignments.planner ?? "",
    coder: snapshot.assignments.coder ?? "",
    reviewer: snapshot.assignments.reviewer ?? "",
    embedding: snapshot.assignments.embedding ?? "",
  };
  if (ROLES.some((role) => fromSaved[role])) {
    return fromSaved;
  }
  return assignmentsFromProfiles(snapshot.profiles);
}

function assignmentsFromProfiles(
  profiles: { id: string; role: string }[],
): Record<ModelRole, string> {
  const byRole = Object.fromEntries(profiles.map((profile) => [profile.role, profile.id]));
  return {
    planner: byRole.planner ?? "",
    coder: byRole.coder ?? "",
    reviewer: byRole.reviewer ?? "",
    embedding: byRole.embedding ?? "",
  };
}
