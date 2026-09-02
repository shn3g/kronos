/** @vitest-environment node */
// SPDX-License-Identifier: AGPL-3.0-or-later

import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { readWebEngineBinding } from "./webEngineBinding";

describe("readWebEngineBinding", () => {
  it("reads the loopback URL and token from config files without extra fields", () => {
    const configDir = mkdtempSync(join(tmpdir(), "kronos-web-engine-"));
    mkdirSync(configDir, { recursive: true });
    writeFileSync(
      join(configDir, "engine_ready.json"),
      JSON.stringify({ base_url: "http://127.0.0.1:7431" }),
    );
    writeFileSync(join(configDir, "install.json"), JSON.stringify({ auth_token: "secret-token" }));

    expect(readWebEngineBinding(configDir, {})).toEqual({
      baseUrl: "http://127.0.0.1:7431",
      token: "secret-token",
    });
  });

  it("rejects a non-loopback URL", () => {
    const configDir = mkdtempSync(join(tmpdir(), "kronos-web-engine-"));
    writeFileSync(
      join(configDir, "engine_ready.json"),
      JSON.stringify({ base_url: "http://example.com:80" }),
    );
    writeFileSync(join(configDir, "install.json"), JSON.stringify({ auth_token: "secret-token" }));

    expect(readWebEngineBinding(configDir, {})).toBeNull();
  });

  it("reads KRONOS_ENGINE_URL and KRONOS_AUTH_TOKEN from the environment", () => {
    const configDir = mkdtempSync(join(tmpdir(), "kronos-web-engine-"));
    expect(
      readWebEngineBinding(configDir, {
        KRONOS_ENGINE_URL: "http://127.0.0.1:7431",
        KRONOS_AUTH_TOKEN: "env-token",
      }),
    ).toEqual({
      baseUrl: "http://127.0.0.1:7431",
      token: "env-token",
    });
  });

  it("rejects a non-loopback URL from the environment", () => {
    const configDir = mkdtempSync(join(tmpdir(), "kronos-web-engine-"));
    expect(
      readWebEngineBinding(configDir, {
        KRONOS_ENGINE_URL: "http://example.com:80",
        KRONOS_AUTH_TOKEN: "env-token",
      }),
    ).toBeNull();
  });
});
