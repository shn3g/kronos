import { describe, expect, it } from "vitest";
import { toolCardLabel } from "./toolCard";

describe("toolCardLabel", () => {
  it("uses a human name and a text status, not color alone", () => {
    expect(toolCardLabel("search_index", "ok")).toBe("Search index · done");
    expect(toolCardLabel("read_file", "error")).toBe("Read file · failed");
    expect(toolCardLabel("create_goal", "running")).toBe("Create goal · running");
  });
});
