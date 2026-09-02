/** @vitest-environment node */
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it, vi } from "vitest";
import { bootWithEngine, stopWithEngineStack } from "./startWithEngine";

function killable() {
  const kill = vi.fn(() => true);
  return { kill };
}

function closable() {
  const close = vi.fn(() => undefined);
  return { close };
}

describe("with-engine stack cleanup", () => {
  it("kills a no-op stack without throwing", () => {
    expect(() => stopWithEngineStack({})).not.toThrow();
  });

  it("tears down the mock and engine when the engine never becomes ready", async () => {
    const mock = closable();
    const engine = killable();
    const spawnVite = vi.fn(killable);

    await expect(
      bootWithEngine({
        startMock: async () => mock,
        spawnEngine: () => engine,
        spawnVite,
        waitForEngine: async () => {
          throw new Error("KRONOS_READY was not printed");
        },
        waitForVite: async () => undefined,
      }),
    ).rejects.toThrow(/KRONOS_READY/);

    expect(spawnVite).not.toHaveBeenCalled();
    expect(engine.kill).toHaveBeenCalledWith("SIGTERM");
    expect(mock.close).toHaveBeenCalled();
  });

  it("tears down engine, vite, and mock when the UI never becomes reachable", async () => {
    const mock = closable();
    const engine = killable();
    const vite = killable();

    await expect(
      bootWithEngine({
        startMock: async () => mock,
        spawnEngine: () => engine,
        spawnVite: () => vite,
        waitForEngine: async () => undefined,
        waitForVite: async () => {
          throw new Error("timed out waiting for http://127.0.0.1:1420/");
        },
      }),
    ).rejects.toThrow(/timed out waiting/);

    expect(engine.kill).toHaveBeenCalledWith("SIGTERM");
    expect(vite.kill).toHaveBeenCalledWith("SIGTERM");
    expect(mock.close).toHaveBeenCalled();
  });

  it("leaves the stack running after a successful boot until stop is called", async () => {
    const mock = closable();
    const engine = killable();
    const vite = killable();

    const { stop } = await bootWithEngine({
      startMock: async () => mock,
      spawnEngine: () => engine,
      spawnVite: () => vite,
      waitForEngine: async () => undefined,
      waitForVite: async () => undefined,
    });

    expect(engine.kill).not.toHaveBeenCalled();
    expect(vite.kill).not.toHaveBeenCalled();
    expect(mock.close).not.toHaveBeenCalled();

    stop();

    expect(engine.kill).toHaveBeenCalledWith("SIGTERM");
    expect(vite.kill).toHaveBeenCalledWith("SIGTERM");
    expect(mock.close).toHaveBeenCalled();
  });
});
