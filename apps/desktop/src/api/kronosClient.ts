// SPDX-License-Identifier: AGPL-3.0-or-later

import type { EngineConnectionState } from "../engine/client";

export const DESKTOP_CLIENT_VERSION = "0.6.0";

export interface EngineLocateResult {
  baseUrl: string;
  token: string;
}

export async function probeEngineState(options: {
  baseUrl: string;
  token: string;
  clientVersion?: string;
  fetchImpl?: typeof fetch;
}): Promise<EngineConnectionState> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const clientVersion = options.clientVersion ?? DESKTOP_CLIENT_VERSION;
  const headers: Record<string, string> = {
    "X-Kronos-Client-Version": clientVersion,
  };
  if (options.token.trim().length > 0) {
    headers.Authorization = `Bearer ${options.token}`;
  }
  try {
    const health = await fetchImpl(`${trimSlash(options.baseUrl)}/health`, { headers });
    if (!health.ok) {
      return { status: "unavailable" };
    }
    const healthBody = (await health.json()) as { status?: string };
    if (healthBody.status !== "ok") {
      return { status: "unavailable" };
    }

    const version = await fetchImpl(`${trimSlash(options.baseUrl)}/version`, { headers });
    if (!version.ok) {
      return { status: "unavailable" };
    }
    const body = (await version.json()) as {
      engine_version?: string;
      compatible?: boolean;
    };
    if (body.compatible !== true) {
      return {
        status: "incompatible",
        clientVersion,
        engineVersion: typeof body.engine_version === "string" ? body.engine_version : "unknown",
      };
    }
    if (typeof body.engine_version !== "string" || body.engine_version.length === 0) {
      return { status: "unavailable" };
    }
    return { status: "ready", version: body.engine_version };
  } catch {
    return { status: "unavailable" };
  }
}

export async function pollEngineEvents(options: {
  baseUrl: string;
  token: string;
  after?: number;
  fetchImpl?: typeof fetch;
}): Promise<{ events: EngineEvent[]; headSeq: number } | null> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const after = options.after ?? 0;
  try {
    const response = await fetchImpl(
      `${trimSlash(options.baseUrl)}/events?after=${after}`,
      {
        headers: { Authorization: `Bearer ${options.token}` },
      },
    );
    if (!response.ok) {
      return null;
    }
    const body = (await response.json()) as {
      events?: EngineEvent[];
      head_seq?: number;
    };
    if (!Array.isArray(body.events) || typeof body.head_seq !== "number") {
      return null;
    }
    return { events: body.events, headSeq: body.head_seq };
  } catch {
    return null;
  }
}

export interface EngineEvent {
  seq: number;
  id: string;
  type: string;
  payload: Record<string, unknown>;
  recorded_at: string;
}

function trimSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}
