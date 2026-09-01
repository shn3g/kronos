/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  editorLineLabels,
  fileDraftIsDirty,
  fileFindStatusLabel,
  findInFileText,
  insertEditorText,
  nextFileFindIndex,
  parseGoToLineInput,
  replaceAllInFileText,
  replaceInFileMatch,
  selectionForLineColumn,
  workspaceSearchHitLabel,
  workspaceSearchHitSnippet,
} from "./fileEditor";

describe("fileDraftIsDirty", () => {
  it("is clean when draft matches the last saved text", () => {
    expect(fileDraftIsDirty("print(1)\n", "print(1)\n")).toBe(false);
  });

  it("is dirty when the draft differs", () => {
    expect(fileDraftIsDirty("print(1)\n", "print(2)\n")).toBe(true);
  });

  it("is clean when either side has not loaded yet", () => {
    expect(fileDraftIsDirty(null, "print(1)\n")).toBe(false);
    expect(fileDraftIsDirty("print(1)\n", null)).toBe(false);
  });
});

describe("insertEditorText", () => {
  it("replaces the selected range and places the caret after the insertion", () => {
    expect(insertEditorText("abef", 2, 2, "cd")).toEqual({ content: "abcdef", caret: 4 });
    expect(insertEditorText("aXXXf", 1, 4, "bcd")).toEqual({ content: "abcdf", caret: 4 });
  });
});

describe("editorLineLabels", () => {
  it("numbers each line, including a trailing empty line", () => {
    expect(editorLineLabels("")).toEqual(["1"]);
    expect(editorLineLabels("print(1)\n")).toEqual(["1", "2"]);
    expect(editorLineLabels("a\nb\nc")).toEqual(["1", "2", "3"]);
  });
});

describe("findInFileText", () => {
  it("returns nothing for an empty query", () => {
    expect(findInFileText("print(1)\n", "")).toEqual([]);
    expect(findInFileText("print(1)\n", "   ")).toEqual([]);
  });

  it("finds case-insensitive literal matches without overlapping", () => {
    expect(findInFileText("Alpha\nalpha\nALPHA\n", "alpha")).toEqual([
      { start: 0, end: 5 },
      { start: 6, end: 11 },
      { start: 12, end: 17 },
    ]);
    expect(findInFileText("aaa", "aa")).toEqual([{ start: 0, end: 2 }]);
  });

  it("returns nothing when the query is not in the file", () => {
    expect(findInFileText("print(1)\n", "zzz")).toEqual([]);
  });

  it("can require the same letter case", () => {
    expect(findInFileText("Alpha\nalpha\n", "alpha", { caseSensitive: true })).toEqual([
      { start: 6, end: 11 },
    ]);
  });
});

describe("nextFileFindIndex", () => {
  it("wraps around the match list", () => {
    expect(nextFileFindIndex(0, -1, 3)).toBe(2);
    expect(nextFileFindIndex(2, 1, 3)).toBe(0);
    expect(nextFileFindIndex(1, 1, 3)).toBe(2);
  });

  it("stays at zero when there are no matches", () => {
    expect(nextFileFindIndex(4, 1, 0)).toBe(0);
  });
});

describe("fileFindStatusLabel", () => {
  it("explains empty, missing, and counted matches", () => {
    expect(fileFindStatusLabel("", 0, 0)).toBe("");
    expect(fileFindStatusLabel("print", 0, 0)).toBe("No matches.");
    expect(fileFindStatusLabel("print", 3, 1)).toBe("2 of 3");
  });
});

describe("replaceInFileMatch", () => {
  it("replaces one span and places the caret after the insertion", () => {
    expect(replaceInFileMatch("alpha beta alpha", { start: 0, end: 5 }, "one")).toEqual({
      content: "one beta alpha",
      caret: 3,
    });
  });

  it("leaves the file unchanged when the span is empty or out of range", () => {
    expect(replaceInFileMatch("alpha", { start: 9, end: 12 }, "x")).toEqual({
      content: "alpha",
      caret: 5,
    });
  });
});

describe("replaceAllInFileText", () => {
  it("replaces every case-insensitive match", () => {
    expect(replaceAllInFileText("Alpha\nalpha\n", "alpha", "beta")).toEqual({
      content: "beta\nbeta\n",
      count: 2,
    });
  });

  it("does nothing when the query is empty or nothing matches", () => {
    expect(replaceAllInFileText("alpha", "  ", "x")).toEqual({ content: "alpha", count: 0 });
    expect(replaceAllInFileText("alpha", "zzz", "x")).toEqual({ content: "alpha", count: 0 });
  });

  it("can replace only the same letter case", () => {
    expect(replaceAllInFileText("Alpha\nalpha\n", "alpha", "beta", { caseSensitive: true })).toEqual({
      content: "Alpha\nbeta\n",
      count: 1,
    });
  });
});

describe("parseGoToLineInput", () => {
  it("reads a 1-based line, and an optional column", () => {
    expect(parseGoToLineInput("12")).toEqual({ line: 12, column: null });
    expect(parseGoToLineInput(" 12:5 ")).toEqual({ line: 12, column: 5 });
    expect(parseGoToLineInput("12,3")).toEqual({ line: 12, column: 3 });
  });

  it("rejects blank, zero, and non-numeric input", () => {
    expect(parseGoToLineInput("")).toBeNull();
    expect(parseGoToLineInput("0")).toBeNull();
    expect(parseGoToLineInput("line 2")).toBeNull();
    expect(parseGoToLineInput("2:0")).toBeNull();
  });
});

describe("selectionForLineColumn", () => {
  it("selects the requested line, or places a caret at the column", () => {
    expect(selectionForLineColumn("alpha\nbeta\ngamma\n", 2, null)).toEqual({
      start: 6,
      end: 10,
      line: 2,
    });
    expect(selectionForLineColumn("alpha\nbeta\ngamma\n", 3, 2)).toEqual({
      start: 12,
      end: 12,
      line: 3,
    });
  });

  it("clamps a line past the end of the file", () => {
    expect(selectionForLineColumn("alpha\nbeta\n", 99, null)).toEqual({
      start: 11,
      end: 11,
      line: 3,
    });
  });
});

describe("workspaceSearchHitLabel", () => {
  it("names a hit as path and 1-based line", () => {
    expect(workspaceSearchHitLabel("src/app.py", 2)).toBe("src/app.py:2");
    expect(workspaceSearchHitLabel("  README.md  ", 0)).toBe("README.md:1");
    expect(workspaceSearchHitLabel("", 4)).toBe("");
  });
});

describe("workspaceSearchHitSnippet", () => {
  it("collapses a hit to one short line of text", () => {
    expect(workspaceSearchHitSnippet("  def connect():\n    pass  ")).toBe("def connect(): pass");
    expect(workspaceSearchHitSnippet("   ")).toBe("");
    expect(workspaceSearchHitSnippet("a".repeat(130)).length).toBe(120);
  });
});
