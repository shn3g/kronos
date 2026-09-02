// SPDX-License-Identifier: AGPL-3.0-or-later

/** @vitest-environment node */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { UPDATER_PUBKEY, isUpdaterSigningConfigured } from "./updaterConfig";

const tauriConf = JSON.parse(
  readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "../../../src-tauri/tauri.conf.json"),
    "utf8",
  ),
) as { plugins?: { updater?: { pubkey?: string } } };

describe("updaterConfig", () => {
  it("mirrors plugins.updater.pubkey in tauri.conf.json", () => {
    expect(UPDATER_PUBKEY).toBe(tauriConf.plugins?.updater?.pubkey ?? "");
  });

  it("treats an empty pubkey as unsigned", () => {
    expect(isUpdaterSigningConfigured("")).toBe(false);
    expect(isUpdaterSigningConfigured("   ")).toBe(false);
  });
});
