/** @vitest-environment node */
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { webEngineProxyPlugin } from "./webEngineProxy";

describe("webEngineProxyPlugin", () => {
  it("hooks the Vite dev server only, not vite preview", () => {
    const plugin = webEngineProxyPlugin();
    expect(plugin.name).toBe("kronos-web-engine-proxy");
    expect(plugin.configureServer).toEqual(expect.any(Function));
    expect(plugin.configurePreviewServer).toBeUndefined();
  });
});
