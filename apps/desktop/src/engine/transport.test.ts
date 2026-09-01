// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it, vi } from "vitest";
import { requestEngineJson } from "./transport";

describe("requestEngineJson", () => {
  it("uses the Tauri sidecar when invoke succeeds and never sends a bearer token to fetch", async () => {
    const fetchImpl = vi.fn();
    const result = await requestEngineJson("GET", "/ops/doctor", undefined, {
      invokeJson: async () => ({ status: 200, body: "{\"ready\":true}" }),
      fetchImpl,
    });

    expect(result).toEqual({ status: 200, body: "{\"ready\":true}" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("falls back to the same-origin web engine without putting a token in the renderer", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("authorization")).toBeNull();
      expect(String(input)).toBe("/kronos-engine/chat/sessions");
      return new Response("{\"sessions\":[]}", { status: 200 });
    });

    const result = await requestEngineJson("GET", "/chat/sessions", undefined, {
      invokeJson: async () => {
        throw new Error("not in tauri");
      },
      fetchImpl,
    });

    expect(result.status).toBe(200);
    expect(result.body).toContain("sessions");
    expect(fetchImpl).toHaveBeenCalled();
  });
});
