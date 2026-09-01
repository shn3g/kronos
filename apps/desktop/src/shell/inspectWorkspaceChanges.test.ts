// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { inspectWorkspaceChanges } from "./inspectWorkspaceChanges";

describe("inspectWorkspaceChanges", () => {
  it("keeps the latest write per path and lists newest files first", () => {
    const changes = inspectWorkspaceChanges(
      [
        { path: "src/old.py", summary: "Wrote src/old.py", repositoryId: "repo_alpha" },
        { path: "src/app.py", summary: "Wrote src/app.py first", repositoryId: "repo_alpha" },
        { path: "src/app.py", summary: "Wrote src/app.py", repositoryId: "repo_alpha" },
      ],
      "repo_alpha",
    );
    expect(changes).toEqual([
      { path: "src/app.py", summary: "Wrote src/app.py" },
      { path: "src/old.py", summary: "Wrote src/old.py" },
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
    expect(changes).toEqual([{ path: "a.py", summary: "Wrote a.py" }]);
  });
});
