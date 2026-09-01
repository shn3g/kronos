// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatMarkdown } from "./ChatMarkdown";

describe("ChatMarkdown", () => {
  it("copies a fenced code block onto the clipboard", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<ChatMarkdown source={"Staff is **missing**.\n\n```ts\nconst ok = false;\n```\n"} />);

    await user.click(screen.getByRole("button", { name: /^copy$/i }));

    expect(writeText).toHaveBeenCalledWith("const ok = false;");
    expect(screen.getByRole("button", { name: /^copied$/i })).toBeInTheDocument();
  });

  it("says so when the clipboard is blocked", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<ChatMarkdown source={"```ts\nconst ok = false;\n```\n"} />);

    await user.click(screen.getByRole("button", { name: /^copy$/i }));

    expect(
      await screen.findByText("Could not copy. Select the text and copy it yourself."),
    ).toBeInTheDocument();
  });
});
