// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EngineGate } from "./EngineGate";

const CRASH_LOG = "== engine-sidecar.log ==\nTraceback (most recent call last)\nRuntimeError: boom\n";

describe("EngineGate", () => {
  it("shows crash details when Kronos stopped and a log is available", () => {
    render(<EngineGate starting={false} crashLog={CRASH_LOG} />);

    expect(screen.getByRole("heading", { name: "Kronos stopped unexpectedly" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Kronos is restarting. If this keeps happening, copy the details below and open an issue.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Show details")).toBeInTheDocument();
    expect(screen.getByText(/RuntimeError: boom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy details" })).toBeInTheDocument();
  });

  it("copies the log when Copy details is clicked", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<EngineGate starting={false} crashLog={CRASH_LOG} />);
    await user.click(screen.getByRole("button", { name: "Copy details" }));

    expect(writeText).toHaveBeenCalledWith(CRASH_LOG);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("says so when the clipboard is blocked", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });

    render(<EngineGate starting={false} crashLog={CRASH_LOG} />);
    await user.click(screen.getByRole("button", { name: "Copy details" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Could not copy. Select the text and copy it yourself.",
    );
  });

  it("omits the details block when no log is available", () => {
    render(<EngineGate starting={false} crashLog={null} />);

    expect(screen.getByRole("heading", { name: "Kronos stopped unexpectedly" })).toBeInTheDocument();
    expect(screen.queryByText("Show details")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy details" })).not.toBeInTheDocument();
  });

  it("never shows crash details while Kronos is starting", () => {
    render(<EngineGate starting crashLog={CRASH_LOG} />);

    expect(screen.getByRole("heading", { name: "Starting Kronos" })).toBeInTheDocument();
    expect(screen.queryByText("Show details")).not.toBeInTheDocument();
    expect(screen.queryByText(/RuntimeError: boom/)).not.toBeInTheDocument();
  });
});
