// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { inspectWorkspaceChanges, visibleInspectorChanges } from "./inspectWorkspaceChanges";

describe("inspectWorkspaceChanges", () => {
  it("keeps the latest write per path and lists newest files first", () => {
    const changes = inspectWorkspaceChanges(
      [
        { path: "src/old.py", summary: "Wrote src/old.py", repositoryId: "repo_alpha" },
        {
          path: "src/app.py",
          summary: "Wrote src/app.py first",
          patch: "+first\n",
          repositoryId: "repo_alpha",
        },
        {
          path: "src/app.py",
          summary: "Wrote src/app.py",
          patch: "--- a\n+++ b\n+second\n",
          repositoryId: "repo_alpha",
        },
      ],
      "repo_alpha",
    );
    expect(changes).toEqual([
      { path: "src/app.py", summary: "Wrote src/app.py", patch: "--- a\n+++ b\n+second\n" },
      { path: "src/old.py", summary: "Wrote src/old.py", patch: "" },
    ]);
  });

  it("hides diffs from other workspaces", () => {
    const changes = inspectWorkspaceChanges(
      [
        { path: "a.py", summary: "Wrote a.py", repositoryId: "repo_alpha" },
        { path: "b.py", summary: "Wrote b.py", repositoryId: "repo_beta" },
      ],
      "repo_alpha",
    );
    expect(changes).toEqual([{ path: "a.py", summary: "Wrote a.py", patch: "" }]);
  });

  it("limits This turn to chat writes and keeps All unchanged", () => {
    const changes = [
      { path: "src/App.tsx", summary: "Modified src/App.tsx", patch: "+a\n", fromChat: true },
      { path: "notes.md", summary: "Modified notes.md", patch: "+b\n", fromChat: false },
    ];

    expect(visibleInspectorChanges(changes, "turn")).toEqual([changes[0]]);
    expect(visibleInspectorChanges(changes, "all")).toEqual(changes);
  });
});
