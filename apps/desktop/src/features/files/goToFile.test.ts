// SPDX-License-Identifier: AGPL-3.0-or-later
/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  GO_TO_FILE_RESULT_LIMIT,
  clampGoToFileIndex,
  nextGoToFileIndex,
  rankWorkspaceFilePaths,
} from "./goToFile";

describe("rankWorkspaceFilePaths", () => {
  it("drops empty paths, duplicates, and parent-directory escapes", () => {
    expect(
      rankWorkspaceFilePaths(["", "src/app.py", "src/app.py", "../secret.txt", "README.md"], ""),
    ).toEqual(["src/app.py", "README.md"]);
  });

  it("returns original unique paths when the query is empty, capped at the limit", () => {
    const paths = Array.from({ length: GO_TO_FILE_RESULT_LIMIT + 5 }, (_, index) => `f${index}.ts`);

    expect(rankWorkspaceFilePaths(paths, "  ")).toHaveLength(GO_TO_FILE_RESULT_LIMIT);
    expect(rankWorkspaceFilePaths(paths, "", 2)).toEqual(["f0.ts", "f1.ts"]);
  });

  it("prefers a basename prefix over a later substring", () => {
    expect(
      rankWorkspaceFilePaths(["src/mapper.py", "src/app.py", "src/App.tsx", "README.md"], "app"),
    ).toEqual(["src/app.py", "src/App.tsx", "src/mapper.py"]);
  });

  it("matches a fuzzy subsequence when the query is not a substring", () => {
    expect(rankWorkspaceFilePaths(["src/app.py", "README.md"], "sapy")).toEqual(["src/app.py"]);
  });

  it("returns an empty list when nothing matches", () => {
    expect(rankWorkspaceFilePaths(["src/app.py"], "zzz")).toEqual([]);
  });
});

describe("nextGoToFileIndex", () => {
  it("wraps around the result list", () => {
    expect(nextGoToFileIndex(0, -1, 3)).toBe(2);
    expect(nextGoToFileIndex(2, 1, 3)).toBe(0);
    expect(nextGoToFileIndex(1, 1, 3)).toBe(2);
  });

  it("stays at zero when there are no results", () => {
    expect(nextGoToFileIndex(4, 1, 0)).toBe(0);
  });
});

describe("clampGoToFileIndex", () => {
  it("keeps the highlight inside the result list", () => {
    expect(clampGoToFileIndex(9, 3)).toBe(2);
    expect(clampGoToFileIndex(-1, 3)).toBe(0);
    expect(clampGoToFileIndex(1, 0)).toBe(0);
  });
});
