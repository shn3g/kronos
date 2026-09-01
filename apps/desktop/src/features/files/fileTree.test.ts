/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { fileTreeFromPaths, filterFileTree, flattenFileTree } from "./fileTree";

describe("fileTreeFromPaths", () => {
  it("nests files under folders and sorts folders before files", () => {
    const tree = fileTreeFromPaths(["README.md", "src/app.py", "src/util.py", "docs/guide.md"]);

    expect(tree.map((node) => node.name)).toEqual(["docs", "src", "README.md"]);
    expect(tree[1]).toEqual({
      name: "src",
      path: "src",
      kind: "folder",
      children: [
        { name: "app.py", path: "src/app.py", kind: "file", children: [] },
        { name: "util.py", path: "src/util.py", kind: "file", children: [] },
      ],
    });
  });

  it("ignores empty paths and parent-directory escapes", () => {
    expect(fileTreeFromPaths(["", "../secret.txt", "ok.py"])).toEqual([
      { name: "ok.py", path: "ok.py", kind: "file", children: [] },
    ]);
  });
});

describe("filterFileTree", () => {
  it("keeps folders that still have matching descendants", () => {
    const tree = fileTreeFromPaths(["src/app.py", "src/util.py", "README.md"]);

    expect(filterFileTree(tree, "app").map((node) => node.path)).toEqual(["src"]);
    expect(filterFileTree(tree, "app")[0]?.children.map((node) => node.path)).toEqual(["src/app.py"]);
  });
});

describe("flattenFileTree", () => {
  it("emits expanded folders and hides collapsed children", () => {
    const tree = fileTreeFromPaths(["src/app.py", "README.md"]);

    expect(flattenFileTree(tree, new Set()).map((row) => row.path)).toEqual(["src", "README.md"]);
    expect(flattenFileTree(tree, new Set(["src"])).map((row) => `${row.depth}:${row.path}`)).toEqual([
      "0:src",
      "1:src/app.py",
      "0:README.md",
    ]);
  });
});
