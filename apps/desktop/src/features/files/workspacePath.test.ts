/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  ancestorFolderPaths,
  looksLikeWorkspaceFilePath,
  safeWorkspaceRelPath,
} from "./workspacePath";

describe("safeWorkspaceRelPath", () => {
  it("normalizes slashes and strips a leading slash", () => {
    expect(safeWorkspaceRelPath("src\\app.py")).toBe("src/app.py");
    expect(safeWorkspaceRelPath("/src/app.py")).toBe("src/app.py");
  });

  it("rejects empty, parent, and .git segments", () => {
    expect(safeWorkspaceRelPath("")).toBe("");
    expect(safeWorkspaceRelPath("   ")).toBe("");
    expect(safeWorkspaceRelPath("../secret.txt")).toBe("");
    expect(safeWorkspaceRelPath("src/../secret.txt")).toBe("");
    expect(safeWorkspaceRelPath(".git/config")).toBe("");
  });
});

describe("ancestorFolderPaths", () => {
  it("lists folders that must be expanded to reveal a nested file", () => {
    expect(ancestorFolderPaths("src/app.py")).toEqual(["src"]);
    expect(ancestorFolderPaths("a/b/c.ts")).toEqual(["a", "a/b"]);
    expect(ancestorFolderPaths("README.md")).toEqual([]);
  });

  it("returns nothing for an unsafe path", () => {
    expect(ancestorFolderPaths("../secret.txt")).toEqual([]);
  });
});

describe("looksLikeWorkspaceFilePath", () => {
  it("accepts relative files with a slash or a file extension", () => {
    expect(looksLikeWorkspaceFilePath("src/ok.ts")).toBe(true);
    expect(looksLikeWorkspaceFilePath("package.json")).toBe(true);
  });

  it("rejects identifiers and parent escapes", () => {
    expect(looksLikeWorkspaceFilePath("const")).toBe(false);
    expect(looksLikeWorkspaceFilePath("ts")).toBe(false);
    expect(looksLikeWorkspaceFilePath("../secret.txt")).toBe(false);
  });
});
