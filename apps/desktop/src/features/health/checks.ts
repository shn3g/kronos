// SPDX-License-Identifier: AGPL-3.0-or-later

export interface HealthCheck {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
}

export function checksFromLocal(input: {
  engineReady: boolean;
  modelReady: boolean;
  workspaceReady: boolean;
  indexReady: boolean;
}): HealthCheck[] {
  return [
    {
      id: "engine",
      label: "Engine",
      ok: input.engineReady,
      detail: input.engineReady
        ? "The local engine is running."
        : "The local engine is not connected.",
    },
    {
      id: "model",
      label: "Model",
      ok: input.modelReady,
      detail: input.modelReady ? "A planner model is assigned." : "Connect a model before chatting.",
    },
    {
      id: "workspace",
      label: "Workspace",
      ok: input.workspaceReady,
      detail: input.workspaceReady
        ? "A git folder is enrolled."
        : "Open a git folder to index and edit code.",
    },
    {
      id: "index",
      label: "Index",
      ok: input.indexReady,
      detail: input.indexReady
        ? "The local search index is healthy."
        : "The search index needs a rebuild.",
    },
    {
      id: "secrets",
      label: "Secrets",
      ok: true,
      detail: "API keys stay in the operating system secret store.",
    },
  ];
}
