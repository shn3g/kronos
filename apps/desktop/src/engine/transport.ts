// SPDX-License-Identifier: AGPL-3.0-or-later

export interface EngineJsonResponse {
  status: number;
  body: string;
}

export interface EngineTransport {
  invokeJson?: (method: string, path: string, body?: unknown) => Promise<EngineJsonResponse>;
  fetchImpl?: typeof fetch;
  webBase?: string;
}

const WEB_ENGINE_BASE = "/kronos-engine";
const CLIENT_VERSION = "0.1.0";

export async function requestEngineJson(
  method: string,
  path: string,
  body?: unknown,
  transport: EngineTransport = {},
): Promise<EngineJsonResponse> {
  const invoked = await invokeSidecar(method, path, body, transport);
  if (invoked !== null) {
    return invoked;
  }
  return fetchWebEngine(method, path, body, transport);
}

async function invokeSidecar(
  method: string,
  path: string,
  body: unknown,
  transport: EngineTransport,
): Promise<EngineJsonResponse | null> {
  if (transport.invokeJson) {
    try {
      return await transport.invokeJson(method, path, body);
    } catch {
      return null;
    }
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<EngineJsonResponse>("engine_json", { method, path, body: body ?? null });
  } catch {
    return null;
  }
}

async function fetchWebEngine(
  method: string,
  path: string,
  body: unknown,
  transport: EngineTransport,
): Promise<EngineJsonResponse> {
  const fetchImpl = transport.fetchImpl ?? fetch;
  const base = (transport.webBase ?? WEB_ENGINE_BASE).replace(/\/$/, "");
  const headers: Record<string, string> = {
    "X-Kronos-Client-Version": CLIENT_VERSION,
  };
  let payload: string | undefined;
  if (body !== undefined && body !== null) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  try {
    const init: RequestInit = {
      method,
      headers,
      signal: AbortSignal.timeout(timeoutMs(method, path)),
    };
    if (payload !== undefined) {
      init.body = payload;
    }
    const response = await fetchImpl(`${base}${path}`, init);
    return { status: response.status, body: await response.text() };
  } catch {
    return { status: 0, body: "" };
  }
}

function timeoutMs(method: string, path: string): number {
  if (method === "POST" && /\/chat\/sessions\/[^/]+\/messages$/.test(path)) {
    return 300_000;
  }
  if (method === "POST" && /\/index\/(rebuild|refresh)$/.test(path)) {
    return 180_000;
  }
  if (method === "GET") {
    return 8_000;
  }
  return 30_000;
}
