// SPDX-License-Identifier: AGPL-3.0-or-later
/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  EDITOR_HIGHLIGHT_CHAR_LIMIT,
  editorLanguageFromPath,
  highlightEditorTokens,
} from "./fileHighlight";

describe("editorLanguageFromPath", () => {
  it("maps common source extensions", () => {
    expect(editorLanguageFromPath("src/app.py")).toBe("python");
    expect(editorLanguageFromPath("src/App.tsx")).toBe("typescript");
    expect(editorLanguageFromPath("pkg/main.go")).toBe("go");
    expect(editorLanguageFromPath("README.md")).toBe("markdown");
    expect(editorLanguageFromPath("data.json")).toBe("json");
  });

  it("returns null for unknown or missing extensions", () => {
    expect(editorLanguageFromPath("logo.png")).toBeNull();
    expect(editorLanguageFromPath("Makefile")).toBeNull();
    expect(editorLanguageFromPath("")).toBeNull();
  });
});

describe("highlightEditorTokens", () => {
  it("marks Python keywords, comments, strings, and numbers", () => {
    const marked = highlightEditorTokens(
      'def foo():\n    # hi\n    return "x"\n    return 1\n',
      "python",
    ).filter((token) => token.kind !== "plain");

    expect(marked).toEqual([
      { kind: "keyword", text: "def" },
      { kind: "comment", text: "# hi\n" },
      { kind: "keyword", text: "return" },
      { kind: "string", text: '"x"' },
      { kind: "keyword", text: "return" },
      { kind: "number", text: "1" },
    ]);
  });

  it("marks JavaScript comments and template strings", () => {
    const marked = highlightEditorTokens("const x = `hi`; // c\n", "javascript").filter(
      (token) => token.kind !== "plain",
    );

    expect(marked).toEqual([
      { kind: "keyword", text: "const" },
      { kind: "string", text: "`hi`" },
      { kind: "comment", text: "// c\n" },
    ]);
  });

  it("returns a single plain token when the file is too large to color", () => {
    const content = `def x\n${"a".repeat(EDITOR_HIGHLIGHT_CHAR_LIMIT)}`;
    expect(highlightEditorTokens(content, "python")).toEqual([{ kind: "plain", text: content }]);
  });
});
