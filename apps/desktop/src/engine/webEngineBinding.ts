// SPDX-License-Identifier: AGPL-3.0-or-later

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface WebEngineBinding {
  baseUrl: string;
  token: string;
}

export function kronosConfigDir(env: NodeJS.ProcessEnv = process.env): string {
  const override = env.KRONOS_CONFIG_HOME;
  if (override && override.trim() !== "") {
    return override;
  }
  if (process.platform === "win32") {
    const roaming = env.APPDATA || join(homedir(), "AppData", "Roaming");
    return join(roaming, "kronos");
  }
  if (process.platform === "darwin") {
    return join(homedir(), "Library", "Application Support", "kronos");
  }
  const configHome = env.XDG_CONFIG_HOME || join(homedir(), ".config");
  return join(configHome, "kronos");
}

export function readWebEngineBinding(
  configDir: string,
  env: NodeJS.ProcessEnv = process.env,
): WebEngineBinding | null {
  const fromEnv = envBinding(env);
  if (fromEnv) {
    return fromEnv;
  }
  const ready = readJson(join(configDir, "engine_ready.json"));
  const install = readJson(join(configDir, "install.json"));
  const baseUrl = typeof ready?.base_url === "string" ? ready.base_url.trim() : "";
  const token = typeof install?.auth_token === "string" ? install.auth_token.trim() : "";
  if (baseUrl === "" || token === "") {
    return null;
  }
  if (!baseUrl.startsWith("http://127.0.0.1:") && !baseUrl.startsWith("http://[::1]:")) {
    return null;
  }
  return { baseUrl, token };
}

function envBinding(env: NodeJS.ProcessEnv): WebEngineBinding | null {
  const baseUrl = (env.KRONOS_ENGINE_URL || "").trim();
  const token = (env.KRONOS_AUTH_TOKEN || "").trim();
  if (baseUrl === "" || token === "") {
    return null;
  }
  return { baseUrl, token };
}

function readJson(path: string): Record<string, unknown> | null {
  if (!existsSync(path)) {
    return null;
  }
  try {
    const value = JSON.parse(readFileSync(path, "utf8")) as unknown;
    if (typeof value !== "object" || value === null) {
      return null;
    }
    return value as Record<string, unknown>;
  } catch {
    return null;
  }
}
