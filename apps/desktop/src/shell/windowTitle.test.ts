import { describe, expect, it } from "vitest";
import { setDesktopWindowTitle } from "./windowTitle";

describe("setDesktopWindowTitle", () => {
  it("does not throw when Tauri is not present", async () => {
    await expect(setDesktopWindowTitle("Kronos — alpha")).resolves.toBeUndefined();
  });
});
