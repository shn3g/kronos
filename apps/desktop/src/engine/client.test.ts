/** @vitest-environment node */

import { afterEach, describe, expect, it, vi } from "vitest";
import { createProductionEngineClient } from "./client";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: async () => {
    throw new Error("not in tauri");
  },
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createProductionEngineClient", () => {
  it("fails closed to unavailable when no live engine exists", async () => {
    const client = createProductionEngineClient();
    const state = await client.getState();

    expect(state.status).toBe("unavailable");
    expect(state).not.toMatchObject({ status: "ready" });
  });

  it("falls back to probing /kronos-engine when engine_state invoke throws", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      expect(url.startsWith("/kronos-engine")).toBe(true);
      if (url === "/kronos-engine/health") {
        return new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (url === "/kronos-engine/version") {
        return new Response(JSON.stringify({ engine_version: "0.2.0", compatible: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchImpl);

    const client = createProductionEngineClient();
    await expect(client.getState()).resolves.toEqual({ status: "ready", version: "0.2.0" });
    expect(fetchImpl).toHaveBeenCalled();
  });
});

