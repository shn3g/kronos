/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { fileDraftIsDirty, insertEditorText } from "./fileEditor";

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
