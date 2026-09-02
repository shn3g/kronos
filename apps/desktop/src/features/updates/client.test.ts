/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionUpdatesClient } from "./client";

describe("createProductionUpdatesClient", () => {
  it("loads update status through the engine JSON proxy", async () => {
    const client = createProductionUpdatesClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/ops/updates");
      return {
        status: 200,
        body: JSON.stringify({
          engine_version: "0.1.0",
          client_version: "0.1.0",
          compatible: true,
          signed: false,
          checksums_present: true,
          sbom_present: true,
          provenance_present: true,
        }),
      };
    });
    const status = await client.status();
    expect(status.signed).toBe(false);
    expect(status.checksumsPresent).toBe(true);
    expect(client.updaterSigningConfigured()).toBe(true);
  });
});
