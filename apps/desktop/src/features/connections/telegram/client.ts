// SPDX-License-Identifier: AGPL-3.0-or-later

import { requestEngineJson, type EngineJsonResponse } from "../../../engine/transport";

export interface TelegramStatus {
  tokenPresent: boolean;
  allowedUserIds: number[];
  allowedChatIds: number[];
  defaultRepositoryId: string | null;
  lastUpdateOffset: number;
  botfatherUrl: string;
  setupSteps: string[];
}

export interface TelegramAllowlistInput {
  allowedUserIds: number[];
  allowedChatIds: number[];
  defaultRepositoryId: string | null;
}

export interface TelegramClient {
  status(): Promise<TelegramStatus>;
  saveAllowlist(input: TelegramAllowlistInput): Promise<{ tokenPresent: boolean }>;
  importBotToken(): Promise<{ tokenPresent: boolean }>;
}

export function createProductionTelegramClient(
  request: (
    method: string,
    path: string,
    body?: unknown,
  ) => Promise<EngineJsonResponse> = requestEngineJson,
  importToken: () => Promise<EngineJsonResponse> = importTelegramBotToken,
): TelegramClient {
  return {
    async status() {
      const payload = await jsonRequest(request, "GET", "/telegram/status");
      return mapStatus(payload);
    },
    async saveAllowlist(input) {
      const payload = await jsonRequest(request, "PUT", "/telegram/allowlist", {
        allowed_user_ids: input.allowedUserIds,
        allowed_chat_ids: input.allowedChatIds,
        default_repository_id: input.defaultRepositoryId,
      });
      return { tokenPresent: payload.token_present === true };
    },
    async importBotToken() {
      const response = await importToken();
      if (response.status < 200 || response.status >= 300) {
        throw new Error(`engine request failed: ${response.status}`);
      }
      try {
        const payload = JSON.parse(response.body) as Record<string, unknown>;
        return { tokenPresent: payload.token_present === true };
      } catch {
        return { tokenPresent: false };
      }
    },
  };
}

async function importTelegramBotToken(): Promise<EngineJsonResponse> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<EngineJsonResponse>("import_telegram_bot_token");
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

function mapStatus(raw: Record<string, unknown>): TelegramStatus {
  const users = Array.isArray(raw.allowed_user_ids) ? raw.allowed_user_ids : [];
  const chats = Array.isArray(raw.allowed_chat_ids) ? raw.allowed_chat_ids : [];
  const steps = Array.isArray(raw.setup_steps) ? raw.setup_steps : [];
  const defaultRepo = raw.default_repository_id;
  return {
    tokenPresent: raw.token_present === true,
    allowedUserIds: users.filter((item): item is number => typeof item === "number"),
    allowedChatIds: chats.filter((item): item is number => typeof item === "number"),
    defaultRepositoryId: typeof defaultRepo === "string" && defaultRepo ? defaultRepo : null,
    lastUpdateOffset: typeof raw.last_update_offset === "number" ? raw.last_update_offset : 0,
    botfatherUrl: stringField(raw, "botfather_url") || "https://t.me/BotFather",
    setupSteps: steps.filter((item): item is string => typeof item === "string"),
  };
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
