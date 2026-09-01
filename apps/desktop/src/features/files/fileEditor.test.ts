/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  editorLineLabels,
  fileDraftIsDirty,
  fileFindStatusLabel,
  findInFileText,
  insertEditorText,
  nextFileFindIndex,
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
