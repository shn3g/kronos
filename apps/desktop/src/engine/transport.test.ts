// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it, vi } from "vitest";
import { DESKTOP_CLIENT_VERSION } from "../api/kronosClient";
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
      expect(headers.get("X-Kronos-Client-Version")).toBe(DESKTOP_CLIENT_VERSION);
      expect(String(input)).toBe("/kronos-engine/ops/doctor");
      return new Response("{\"ready\":true}", { status: 200 });
    });

    const result = await requestEngineJson("GET", "/ops/doctor", undefined, {
      invokeJson: async () => {
        throw new Error("not in tauri");
      },
      fetchImpl,
    });

    expect(result.status).toBe(200);
    expect(result.body).toContain("ready");
    expect(fetchImpl).toHaveBeenCalled();
  });

  it("uses a long timeout for index rebuild and refresh POSTs", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.signal).toBeInstanceOf(AbortSignal);
      return new Response("{}", { status: 200 });
    });

    await requestEngineJson(
      "POST",
      "/repositories/repo_alpha/index/rebuild",
      {},
      {
        invokeJson: async () => {
          throw new Error("not in tauri");
        },
        fetchImpl,
      },
    );
    await requestEngineJson(
      "POST",
      "/repositories/repo_alpha/index/refresh",
      {},
      {
        invokeJson: async () => {
          throw new Error("not in tauri");
        },
        fetchImpl,
      },
    );

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});
