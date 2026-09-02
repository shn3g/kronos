// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { parseFenceInfo, renderChatMarkdown } from "./renderChatMarkdown";

describe("parseFenceInfo", () => {
  it("splits a language token from a relative path", () => {
    expect(parseFenceInfo("ts src/ok.ts")).toEqual({ language: "ts", path: "src/ok.ts" });
    expect(parseFenceInfo("ts:src/ok.ts")).toEqual({ language: "ts", path: "src/ok.ts" });
    expect(parseFenceInfo("package.json")).toEqual({ language: "", path: "package.json" });
    expect(parseFenceInfo("ts")).toEqual({ language: "ts", path: "" });
  });

  it("rejects parent segments in a fence path", () => {
    expect(parseFenceInfo("ts ../secret.txt")).toEqual({ language: "ts", path: "" });
  });
});

describe("renderChatMarkdown", () => {
  it("turns fenced code and bold into structured blocks without HTML", () => {
    const blocks = renderChatMarkdown(
      "Staff is **missing**.\n\n```ts\nconst ok = false;\n```\n",
    );

    expect(blocks).toEqual([
      {
        type: "paragraph",
        spans: [
          { type: "text", text: "Staff is " },
          { type: "strong", text: "missing" },
          { type: "text", text: "." },
        ],
      },
      { type: "code", language: "ts", text: "const ok = false;", path: "" },
    ]);
  });

  it("reads a workspace path from the fence line", () => {
    const blocks = renderChatMarkdown("```ts src/ok.ts\nconst ok = false;\n```\n");

    expect(blocks).toEqual([
      { type: "code", language: "ts", text: "const ok = false;", path: "src/ok.ts" },
    ]);
  });

  it("turns headings and lists into structured blocks", () => {
    const blocks = renderChatMarkdown(
      "## Findings\n\n- Staff is **missing**\n- Calendar is early\n\n1. Open the team page\n2. Add one person\n",
    );

    expect(blocks).toEqual([
      {
        type: "heading",
        level: 2,
        spans: [{ type: "text", text: "Findings" }],
      },
      {
        type: "list",
        ordered: false,
        items: [
          [
            { type: "text", text: "Staff is " },
            { type: "strong", text: "missing" },
          ],
          [{ type: "text", text: "Calendar is early" }],
        ],
      },
      {
        type: "list",
        ordered: true,
        items: [
          [{ type: "text", text: "Open the team page" }],
          [{ type: "text", text: "Add one person" }],
        ],
      },
    ]);
  });

  it("keeps raw HTML as text so assistant output cannot inject markup", () => {
    const blocks = renderChatMarkdown('<img src=x onerror="alert(1)">');
    expect(blocks).toEqual([
      {
        type: "paragraph",
        spans: [{ type: "text", text: '<img src=x onerror="alert(1)">' }],
      },
    ]);
  });
});
