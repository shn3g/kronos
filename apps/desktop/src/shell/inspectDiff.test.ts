/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { diffLineSpokenLabel, diffLinesFromPatch } from "./inspectDiff";

describe("diffLinesFromPatch", () => {
  it("returns nothing for an empty patch", () => {
    expect(diffLinesFromPatch("")).toEqual([]);
    expect(diffLinesFromPatch("   ")).toEqual([]);
  });

  it("marks added, removed, hunk, and file header lines", () => {
    expect(
      diffLinesFromPatch("--- a/src/App.tsx\n+++ b/src/App.tsx\n@@ -1,2 +1,2 @@\n context\n-old\n+new\n"),
    ).toEqual([
      { kind: "meta", text: "--- a/src/App.tsx" },
      { kind: "meta", text: "+++ b/src/App.tsx" },
      { kind: "hunk", text: "@@ -1,2 +1,2 @@" },
      { kind: "ctx", text: " context" },
      { kind: "del", text: "-old" },
      { kind: "add", text: "+new" },
    ]);
  });

  it("does not treat a deleted line that starts with dashes as a file header", () => {
    expect(diffLinesFromPatch("---foo\n+bar\n")).toEqual([
      { kind: "del", text: "---foo" },
      { kind: "add", text: "+bar" },
    ]);
  });

  it("keeps a truncated tail when the patch is huge", () => {
    const body = Array.from({ length: 520 }, (_, index) => `+line-${index}`).join("\n");
    const lines = diffLinesFromPatch(body);
    expect(lines).toHaveLength(501);
    expect(lines[0]).toEqual({ kind: "add", text: "+line-0" });
    expect(lines[499]).toEqual({ kind: "add", text: "+line-499" });
    expect(lines[500]).toEqual({ kind: "meta", text: "Diff truncated." });
  });
});

describe("diffLineSpokenLabel", () => {
  it("names added and removed lines without relying on color", () => {
    expect(diffLineSpokenLabel({ kind: "add", text: "+new" })).toBe("Added. new");
    expect(diffLineSpokenLabel({ kind: "del", text: "-old" })).toBe("Removed. old");
    expect(diffLineSpokenLabel({ kind: "hunk", text: "@@ -1 +1 @@" })).toBe("Hunk. @@ -1 +1 @@");
    expect(diffLineSpokenLabel({ kind: "meta", text: "--- a/src/App.tsx" })).toBe("--- a/src/App.tsx");
    expect(diffLineSpokenLabel({ kind: "ctx", text: " keep" })).toBe(" keep");
  });
});
