/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionSettingsClient } from "./client";

describe("createProductionSettingsClient", () => {
  it("does not post tokens or PEMs through engine_json", async () => {
    const bodies: unknown[] = [];
    const client = createProductionSettingsClient(async (method, path, body) => {
      bodies.push({ method, path, body });
      if (path === "/ops/settings") {
        return { status: 200, body: JSON.stringify({ otel_export: false, langfuse_export: false }) };
      }
      if (path === "/ops/doctor") {
        return { status: 200, body: JSON.stringify({ ready: true, findings: ["ok"] }) };
      }
      return {
        status: 200,
        body: JSON.stringify({ path: "C:/tmp/backup", includes_secret_store: false }),
      };
    });
    await client.load();
    await client.save({ otelExport: false, langfuseExport: false });
    await client.doctor();
    await client.backup();
    expect(JSON.stringify(bodies)).not.toMatch(/BEGIN RSA|private_key|bot token|123456789:/i);
    expect(JSON.stringify(bodies)).not.toMatch(/\/telegram\/token/);
  });
});
