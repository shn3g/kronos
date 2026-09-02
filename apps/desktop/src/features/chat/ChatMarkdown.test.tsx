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

  it("applies a fenced block to the workspace path on the fence", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn().mockResolvedValue(undefined);

    render(
      <ChatMarkdown
        source={"```ts src/ok.ts\nconst ok = false;\n```\n"}
        onApply={onApply}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^apply$/i }));

    expect(onApply).toHaveBeenCalledWith("src/ok.ts", "const ok = false;");
    expect(screen.getByRole("button", { name: /^applied$/i })).toBeInTheDocument();
  });

  it("asks for a path when the fence has none", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();

    render(<ChatMarkdown source={"```ts\nconst ok = false;\n```\n"} onApply={onApply} />);

    await user.click(screen.getByRole("button", { name: /^apply$/i }));

    expect(onApply).not.toHaveBeenCalled();
    expect(await screen.findByText("Add a file path to apply this.")).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: /file path/i }), "src/ok.ts");
    await user.click(screen.getByRole("button", { name: /^apply$/i }));

    expect(onApply).toHaveBeenCalledWith("src/ok.ts", "const ok = false;");
  });

  it("says so when apply cannot write the file", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn().mockRejectedValue(new Error("denied"));

    render(
      <ChatMarkdown
        source={"```ts src/ok.ts\nconst ok = false;\n```\n"}
        onApply={onApply}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^apply$/i }));

    expect(
      await screen.findByText("Could not apply that file. Check the path and try again."),
    ).toBeInTheDocument();
  });

  it("opens an inline workspace path from assistant markdown", async () => {
    const user = userEvent.setup();
    const onOpenPath = vi.fn();

    render(
      <ChatMarkdown source={"Look at `src/ok.ts` and `const`."} onOpenPath={onOpenPath} />,
    );

    await user.click(screen.getByRole("button", { name: /open src\/ok\.ts/i }));

    expect(onOpenPath).toHaveBeenCalledWith("src/ok.ts");
    expect(screen.getByText("const").tagName).toBe("CODE");
    expect(screen.queryByRole("button", { name: /open const/i })).not.toBeInTheDocument();
  });

  it("does not open a parent-directory inline path", () => {
    const onOpenPath = vi.fn();

    render(<ChatMarkdown source={"Skip `../secret.txt`."} onOpenPath={onOpenPath} />);

    expect(screen.getByText("../secret.txt").tagName).toBe("CODE");
    expect(screen.queryByRole("button", { name: /open \.\.\/secret\.txt/i })).not.toBeInTheDocument();
  });
});
