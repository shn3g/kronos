/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionNotificationsClient } from "./client";

describe("createProductionNotificationsClient", () => {
  it("loads alerts through the engine JSON proxy", async () => {
    const client = createProductionNotificationsClient(async (method, path) => {
      expect(`${method} ${path}`).toBe("GET /ops/notifications");
      return {
        status: 200,
        body: JSON.stringify({
          items: [{ id: "alert_1", title: "Index degraded", detail: "corrupt cache", severity: "pause" }],
        }),
      };
    });
    const items = await client.list();
    expect(items[0]?.title).toBe("Index degraded");
  });
});
