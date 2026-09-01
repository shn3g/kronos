// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { insertMention, mentionQueryAtCursor, mentionSegments, uniqueMentionPaths } from "./mentionQuery";

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

describe("mentionSegments", () => {
  it("splits @path tokens from surrounding text", () => {
    expect(mentionSegments("Fix @src/App.tsx please")).toEqual([
      { kind: "text", value: "Fix " },
      { kind: "path", value: "src/App.tsx" },
      { kind: "text", value: " please" },
    ]);
  });

  it("leaves email addresses as plain text", () => {
    expect(mentionSegments("mail a@b.com")).toEqual([{ kind: "text", value: "mail a@b.com" }]);
  });
});
