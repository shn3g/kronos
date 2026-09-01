// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionModelsClient,
  type DetectedTool,
  type EmbeddingBackend,
  type ModelProfileOption,
  type ModelRole,
  type ModelsClient,
  type ModelsSnapshot,
  type ResourceLimits,
} from "./client";

export type { ModelsClient } from "./client";

const productionModels = createProductionModelsClient();
const ROLES: ModelRole[] = ["orchestrator", "planner", "coder", "reviewer", "embedding"];

const PROVIDER_PRESETS = [
  {
    name: "OpenAI",
    displayName: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    billed: true,
    modelId: "gpt-4o-mini",
  },
  {
    name: "OpenRouter",
    displayName: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    billed: true,
    modelId: "openai/gpt-4o-mini",
  },
  {
    name: "OpenCode Zen",
    displayName: "OpenCode Zen",
    baseUrl: "https://opencode.ai/zen/v1",
    billed: true,
    modelId: "big-pickle",
  },
  {
    name: "Ollama",
    displayName: "Ollama",
    baseUrl: "http://127.0.0.1:11434/v1",
    billed: false,
    modelId: "llama3",
  },
  {
    name: "LM Studio",
    displayName: "LM Studio",
    baseUrl: "http://127.0.0.1:1234/v1",
    billed: false,
    modelId: "local-model",
  },
] as const;

interface ModelsPageProps {
  engineClient: EngineClient;
  modelsClient?: ModelsClient;
}

interface ProviderForm {
  displayName: string;
  baseUrl: string;
  apiKey: string;
  billed: boolean;
  modelId: string;
}

interface ProfileDraft {
  modelId: string;
  maxTokens: number;
  costCeiling: number;
}

const emptyProviderForm = (): ProviderForm => ({
  displayName: "",
  baseUrl: "",
  apiKey: "",
  billed: false,
  modelId: "",
});

export function ModelsPage({ engineClient, modelsClient }: ModelsPageProps) {
  const client = modelsClient ?? productionModels;
  const [ready, setReady] = useState(false);
  const [snapshot, setSnapshot] = useState<ModelsSnapshot | null>(null);
  const [assignments, setAssignments] = useState<Record<ModelRole, string>>({
    orchestrator: "",
    planner: "",
    coder: "",
    reviewer: "",
    embedding: "",
  });
  const [confirmShared, setConfirmShared] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [providerForm, setProviderForm] = useState<ProviderForm>(emptyProviderForm);
  const [profileDrafts, setProfileDrafts] = useState<Record<string, ProfileDraft>>({});

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
      setProfileDrafts(draftsFromProfiles(next.profiles));
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
        assignments: snapshot?.assignments ?? emptyAssignments(),
        embeddingBackend: snapshot?.embeddingBackend ?? sparseBackend(),
      };
      setSnapshot(next);
      setAssignments(assignmentsFromProfiles(created.profiles));
      setProfileDrafts(draftsFromProfiles(created.profiles));
    } catch {
      setError("Could not register the detected provider.");
    }
  }

  async function onCreateProvider() {
    setError(null);
    setSaved(false);
    try {
      const created = await client.createProvider({
        kind: "openai_compatible",
        displayName: providerForm.displayName,
        baseUrl: providerForm.baseUrl || null,
        billed: providerForm.billed,
        apiKey: providerForm.apiKey || null,
      });
      const next: ModelsSnapshot = {
        detected: snapshot?.detected ?? [],
        profiles: created.profiles,
        assignments: snapshot?.assignments ?? emptyAssignments(),
        embeddingBackend: snapshot?.embeddingBackend ?? sparseBackend(),
      };
      setSnapshot(next);
      setAssignments(assignmentsFromProfiles(created.profiles));
      setProfileDrafts(draftsFromProfiles(created.profiles, providerForm.modelId));
      setProviderForm(emptyProviderForm());
    } catch {
      setError("Could not create the provider.");
    }
  }

  async function onSave() {
    setError(null);
    setSaved(false);
    try {
      if (confirmShared) {
        await client.assign(assignments, { confirmSharedRoles: true });
      } else {
        await client.assign(assignments);
      }
      const refreshed = await client.snapshot();
      setSnapshot(refreshed);
      setAssignments(assignmentsFromSnapshot(refreshed));
      setProfileDrafts(draftsFromProfiles(refreshed.profiles));
      setSaved(true);
    } catch {
      setError("Could not save model assignments.");
    }
  }

  async function onSaveProfile(profile: ModelProfileOption) {
    const draft = profileDrafts[profile.id];
    if (!draft) {
      return;
    }
    setError(null);
    setSaved(false);
    try {
      const limits = limitsFromProfile(profile, draft);
      await client.updateProfile(profile.id, { modelId: draft.modelId, limits });
      const refreshed = await client.snapshot();
      setSnapshot(refreshed);
      setProfileDrafts(draftsFromProfiles(refreshed.profiles));
      setSaved(true);
    } catch {
      setError("Could not save the profile.");
    }
  }

  return (
    <section className="models">
      <p className="page-kicker">Models</p>
      <h1 className="page-title">Models</h1>
      <p className="page-body">
        Assign explicit orchestrator, planner, coder, reviewer, and embedding profiles. Kronos
        never silently falls back to an unapproved or paid model.
      </p>
      {snapshot?.embeddingBackend ? (
        <p className="page-body models__backend">
          {embeddingBackendLabel(snapshot.embeddingBackend)}
        </p>
      ) : null}
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
      <div className="models__presets">
        {PROVIDER_PRESETS.map((preset) => (
          <button
            key={preset.name}
            type="button"
            className="btn-quiet"
            onClick={() => {
              setProviderForm({
                displayName: preset.displayName,
                baseUrl: preset.baseUrl,
                apiKey: "",
                billed: preset.billed,
                modelId: preset.modelId,
              });
            }}
          >
            {preset.name}
          </button>
        ))}
      </div>
      <form
        className="models__form"
        onSubmit={(event) => {
          event.preventDefault();
          void onCreateProvider();
        }}
      >
        <label className="models__field" htmlFor="provider-display-name">
          Display name
          <input
            id="provider-display-name"
            className="wizard__input"
            value={providerForm.displayName}
            onChange={(event) => {
              setProviderForm((current) => ({ ...current, displayName: event.target.value }));
            }}
          />
        </label>
        <label className="models__field" htmlFor="provider-base-url">
          Base URL
          <input
            id="provider-base-url"
            className="wizard__input"
            value={providerForm.baseUrl}
            onChange={(event) => {
              setProviderForm((current) => ({ ...current, baseUrl: event.target.value }));
            }}
          />
        </label>
        <label className="models__field" htmlFor="provider-model-id">
          Suggested model
          <input
            id="provider-model-id"
            className="wizard__input"
            value={providerForm.modelId}
            onChange={(event) => {
              setProviderForm((current) => ({ ...current, modelId: event.target.value }));
            }}
          />
        </label>
        <label className="models__field" htmlFor="provider-api-key">
          API key
          <input
            id="provider-api-key"
            className="wizard__input"
            type="password"
            value={providerForm.apiKey}
            autoComplete="off"
            onChange={(event) => {
              setProviderForm((current) => ({ ...current, apiKey: event.target.value }));
            }}
          />
        </label>
        <label className="models__confirm" htmlFor="provider-billed">
          <input
            id="provider-billed"
            type="checkbox"
            checked={providerForm.billed}
            onChange={(event) => {
              setProviderForm((current) => ({ ...current, billed: event.target.checked }));
            }}
          />
          Billed
        </label>
        <button type="submit" className="btn-quiet">
          Create provider
        </button>
      </form>
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
          Use one local model for all five roles
        </label>
        <button type="submit" className="btn-primary">
          Save assignments
        </button>
      </form>
      {(snapshot?.profiles ?? []).map((profile) => {
        const draft = profileDrafts[profile.id] ?? draftFromProfile(profile);
        return (
          <form
            key={profile.id}
            className="models__form"
            onSubmit={(event) => {
              event.preventDefault();
              void onSaveProfile(profile);
            }}
          >
            <p className="page-body">{profile.displayName}</p>
            <label className="models__field" htmlFor={`profile-model-${profile.id}`}>
              Model id
              <input
                id={`profile-model-${profile.id}`}
                className="wizard__input"
                value={draft.modelId}
                onChange={(event) => {
                  setProfileDrafts((current) => ({
                    ...current,
                    [profile.id]: { ...draft, modelId: event.target.value },
                  }));
                }}
              />
            </label>
            <label className="models__field" htmlFor={`profile-ceiling-${profile.id}`}>
              Cost ceiling
              <input
                id={`profile-ceiling-${profile.id}`}
                className="wizard__input"
                type="number"
                step="any"
                value={draft.costCeiling}
                onChange={(event) => {
                  setProfileDrafts((current) => ({
                    ...current,
                    [profile.id]: { ...draft, costCeiling: Number(event.target.value) },
                  }));
                }}
              />
            </label>
            <label className="models__field" htmlFor={`profile-tokens-${profile.id}`}>
              Max tokens
              <input
                id={`profile-tokens-${profile.id}`}
                className="wizard__input"
                type="number"
                value={draft.maxTokens}
                onChange={(event) => {
                  setProfileDrafts((current) => ({
                    ...current,
                    [profile.id]: { ...draft, maxTokens: Number(event.target.value) },
                  }));
                }}
              />
            </label>
            <button type="submit" className="btn-quiet">
              Save profile
            </button>
          </form>
        );
      })}
      {saved ? <p className="models__saved">Assignments saved.</p> : null}
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}

function embeddingBackendLabel(backend: EmbeddingBackend): string {
  if (backend.kind === "openai_compatible") {
    return `Embedding backend: OpenAI-compatible (${backend.displayName})`;
  }
  if (backend.kind === "onnx") {
    return `Embedding backend: Local ONNX (${backend.displayName})`;
  }
  return `Embedding backend: ${backend.displayName || "Sparse only"}`;
}

function sparseBackend(): EmbeddingBackend {
  return { kind: "none", modelId: "", displayName: "Sparse only" };
}

function emptyAssignments(): Record<ModelRole, string | null> {
  return {
    orchestrator: null,
    planner: null,
    coder: null,
    reviewer: null,
    embedding: null,
  };
}

function assignmentsFromSnapshot(snapshot: ModelsSnapshot): Record<ModelRole, string> {
  const fromSaved: Record<ModelRole, string> = {
    orchestrator: snapshot.assignments.orchestrator ?? "",
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
    orchestrator: byRole.orchestrator ?? "",
    planner: byRole.planner ?? "",
    coder: byRole.coder ?? "",
    reviewer: byRole.reviewer ?? "",
    embedding: byRole.embedding ?? "",
  };
}

function draftFromProfile(profile: ModelProfileOption, modelId = ""): ProfileDraft {
  return {
    modelId: modelId || profile.modelId || "",
    maxTokens: profile.limits?.maxTokens ?? 4096,
    costCeiling: profile.limits?.costCeiling ?? 0,
  };
}

function draftsFromProfiles(
  profiles: ModelProfileOption[],
  modelId = "",
): Record<string, ProfileDraft> {
  return Object.fromEntries(
    profiles.map((profile) => [profile.id, draftFromProfile(profile, modelId)]),
  );
}

function limitsFromProfile(profile: ModelProfileOption, draft: ProfileDraft): ResourceLimits {
  return {
    maxTokens: draft.maxTokens,
    maxAttempts: profile.limits?.maxAttempts ?? 3,
    timeoutSeconds: profile.limits?.timeoutSeconds ?? 120,
    costCeiling: draft.costCeiling,
  };
}
