// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { renderChatMarkdown } from "./renderChatMarkdown";

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
      { type: "code", language: "ts", text: "const ok = false;" },
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
