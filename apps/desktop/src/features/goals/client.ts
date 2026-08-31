// SPDX-License-Identifier: AGPL-3.0-or-later

export interface GoalRecord {
  id: string;
  repositoryId: string;
  title: string;
  state: string;
  source: string;
  riskCeiling: string;
  successCriteria: string;
  nonGoals: string;
  stopReason: string | null;
  schedule: string | null;
  maxAttempts: number;
}

export interface GoalTask {
  id: string;
  goalId: string;
  title: string;
  state: string;
  kind: string;
  stopReason: string | null;
  prUrl: string | null;
  prBase: string | null;
}

export interface GoalDraft {
  repositoryId: string;
  title: string;
  successCriteria: string;
  nonGoals: string;
  riskCeiling: string;
  source: string;
  maxAttempts: number;
}

export interface EngineEvent {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
}

export interface TickResult {
  ok: boolean;
  status: string;
  reason: string;
  taskId: string | null;
  prUrl: string | null;
  terminal: boolean;
}

export interface GoalsClient {
  list(): Promise<GoalRecord[]>;
  create(draft: GoalDraft): Promise<GoalRecord>;
  plan(id: string): Promise<{ goal: GoalRecord; tasks: GoalTask[] }>;
  tick(): Promise<TickResult>;
  get(id: string): Promise<{ goal: GoalRecord; tasks: GoalTask[] }>;
  pollEvents(after: number): Promise<{ events: EngineEvent[]; headSeq: number }>;
}

interface EngineJsonResponse {
  status: number;
  body: string;
}

export function createProductionGoalsClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): GoalsClient {
  return {
    async list() {
      const payload = await jsonRequest(request, "GET", "/goals");
      const items = Array.isArray(payload.goals) ? payload.goals : [];
      return items.map(mapGoal);
    },
    async create(draft) {
      const payload = await jsonRequest(request, "POST", "/goals", {
        repository_id: draft.repositoryId,
        title: draft.title,
        success_criteria: draft.successCriteria,
        non_goals: draft.nonGoals,
        risk_ceiling: draft.riskCeiling,
        source: draft.source,
        max_attempts: draft.maxAttempts,
      });
      return mapGoal(payload);
    },
    async plan(id) {
      const payload = await jsonRequest(request, "POST", `/goals/${id}/plan`);
      const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
      return {
        goal: mapGoal(asRecord(payload.goal)),
        tasks: tasks.map(mapTask),
      };
    },
    async tick() {
      const payload = await jsonRequest(request, "POST", "/goals/tick");
      return {
        ok: Boolean(payload.ok),
        status: stringField(payload, "status"),
        reason: stringField(payload, "reason"),
        taskId: typeof payload.task_id === "string" ? payload.task_id : null,
        prUrl: typeof payload.pr_url === "string" ? payload.pr_url : null,
        terminal: Boolean(payload.terminal),
      };
    },
    async get(id) {
      const payload = await jsonRequest(request, "GET", `/goals/${id}`);
      const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
      return {
        goal: mapGoal(asRecord(payload.goal)),
        tasks: tasks.map(mapTask),
      };
    },
    async pollEvents(after) {
      const payload = await jsonRequest(request, "GET", `/events?after=${after}`);
      const events = Array.isArray(payload.events) ? payload.events : [];
      return {
        events: events.map((item) => {
          const record = asRecord(item);
          return {
            seq: typeof record.seq === "number" ? record.seq : 0,
            type: stringField(record, "type"),
            payload: asRecord(record.payload),
          };
        }),
        headSeq: typeof payload.head_seq === "number" ? payload.head_seq : after,
      };
    },
  };
}

async function requestEngineJson(
  method: string,
  path: string,
  body?: unknown,
): Promise<EngineJsonResponse> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<EngineJsonResponse>("engine_json", { method, path, body: body ?? null });
  } catch {
    return { status: 0, body: "" };
  }
}

async function jsonRequest(
  request: (method: string, path: string, body?: unknown) => Promise<EngineJsonResponse>,
  method: string,
  path: string,
  body?: unknown,
): Promise<Record<string, unknown>> {
  const response = await request(method, path, body);
  if (response.status < 200 || response.status >= 300) {
    throw new Error(`engine request failed: ${response.status}`);
  }
  try {
    return JSON.parse(response.body) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function mapGoal(raw: unknown): GoalRecord {
  const item = asRecord(raw);
  return {
    id: stringField(item, "id"),
    repositoryId: stringField(item, "repository_id"),
    title: stringField(item, "title"),
    state: stringField(item, "state"),
    source: stringField(item, "source"),
    riskCeiling: stringField(item, "risk_ceiling"),
    successCriteria: stringField(item, "success_criteria"),
    nonGoals: stringField(item, "non_goals"),
    stopReason: typeof item.stop_reason === "string" ? item.stop_reason : null,
    schedule: typeof item.schedule === "string" ? item.schedule : null,
    maxAttempts: typeof item.max_attempts === "number" ? item.max_attempts : 0,
  };
}

function mapTask(raw: unknown): GoalTask {
  const item = asRecord(raw);
  return {
    id: stringField(item, "id"),
    goalId: stringField(item, "goal_id"),
    title: stringField(item, "title"),
    state: stringField(item, "state"),
    kind: stringField(item, "kind"),
    stopReason: typeof item.stop_reason === "string" ? item.stop_reason : null,
    prUrl: typeof item.pr_url === "string" ? item.pr_url : null,
    prBase: typeof item.pr_base === "string" ? item.pr_base : null,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
