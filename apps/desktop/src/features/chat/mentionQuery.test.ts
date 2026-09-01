// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { insertMention, mentionQueryAtCursor, uniqueMentionPaths } from "./mentionQuery";

describe("mentionQueryAtCursor", () => {
  it("reads the query after the last @ before the cursor", () => {
    expect(mentionQueryAtCursor("look at @app", 12)).toEqual({ start: 8, query: "app" });
  });

  it("ignores @ once a space follows the query", () => {
    expect(mentionQueryAtCursor("look at @app now", 16)).toBeNull();
  });

  it("does not treat email addresses as mentions", () => {
    expect(mentionQueryAtCursor("mail a@b.com", 12)).toBeNull();
  });
});

describe("insertMention", () => {
  it("replaces the @query with a path token", () => {
    expect(insertMention("fix @ap", 4, "ap", "src/App.tsx")).toBe("fix @src/App.tsx ");
  });
});

describe("uniqueMentionPaths", () => {
  it("keeps the first hit for each path", () => {
    expect(
      uniqueMentionPaths([
        { path: "src/App.tsx" },
        { path: "src/App.tsx" },
        { path: "src/main.tsx" },
      ]),
    ).toEqual(["src/App.tsx", "src/main.tsx"]);
  });
});
