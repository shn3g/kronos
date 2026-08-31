import { describe, expect, it } from "vitest";
import { createProductionEngineClient } from "./client";

describe("createProductionEngineClient", () => {
  it("fails closed to unavailable when no live engine exists", async () => {
    const client = createProductionEngineClient();
    const state = await client.getState();

    expect(state.status).toBe("unavailable");
    expect(state).not.toMatchObject({ status: "ready" });
  });
});
