// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../engine/transport";

export interface IndexStatus {
  repositoryId: string;
  commit: string | null;
  chunkCount: number;
  denseAvailable: boolean;
  indexPath: string;
  ready: boolean;
}

export interface IndexHit {
  path: string;
  startLine: number;
  endLine: number;
  commit: string;
  symbol: string | null;
  rankSources: string[];
  trust: string;
  text: string;
}

export interface IndexClient {
  status(repositoryId: string): Promise<IndexStatus>;
  rebuild(repositoryId: string): Promise<IndexStatus>;
  search(repositoryId: string, query: string): Promise<IndexHit[]>;
}

export function createProductionIndexClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
): IndexClient {
  return {
    async status(repositoryId: string) {
      const payload = await jsonRequest(request, "GET", `/repositories/${repositoryId}/index`);
      return mapStatus(payload);
    },
    async rebuild(repositoryId: string) {
      const payload = await jsonRequest(
        request,
        "POST",
        `/repositories/${repositoryId}/index/rebuild`,
      );
      return mapStatus(payload);
    },
    async search(repositoryId: string, query: string) {
      const payload = await jsonRequest(
        request,
        "GET",
        `/repositories/${repositoryId}/index/search?q=${encodeURIComponent(query)}`,
      );
      const items = Array.isArray(payload.items) ? payload.items : [];
      return items.map(mapHit);
    },
  };
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

function mapStatus(payload: Record<string, unknown>): IndexStatus {
  return {
    repositoryId: stringField(payload, "repository_id"),
    commit: typeof payload.commit === "string" ? payload.commit : null,
    chunkCount: typeof payload.chunk_count === "number" ? payload.chunk_count : 0,
    denseAvailable: payload.dense_available === true,
    indexPath: stringField(payload, "index_path"),
    ready: payload.ready === true,
  };
}

function mapHit(raw: unknown): IndexHit {
  const item = asRecord(raw);
  const sources = Array.isArray(item.rank_sources)
    ? item.rank_sources.filter((value): value is string => typeof value === "string")
    : [];
  return {
    path: stringField(item, "path"),
    startLine: typeof item.start_line === "number" ? item.start_line : 0,
    endLine: typeof item.end_line === "number" ? item.end_line : 0,
    commit: stringField(item, "commit"),
    symbol: typeof item.symbol === "string" ? item.symbol : null,
    rankSources: sources,
    trust: stringField(item, "trust"),
    text: stringField(item, "text"),
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
