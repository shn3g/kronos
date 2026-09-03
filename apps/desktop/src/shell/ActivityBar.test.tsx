// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ActivityBar } from "./ActivityBar";

describe("ActivityBar", () => {
  it("shows a text badge and aria-label when notifications are unread", () => {
    render(
      <ActivityBar active="chat" notificationCount={3} onSelect={vi.fn()} />,
    );

    const settings = screen.getByRole("button", { name: /settings, 3 notifications/i });
    expect(settings).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("omits the badge when there are no notifications", () => {
    render(<ActivityBar active="chat" notificationCount={0} onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: /^settings$/i })).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("selects an activity", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ActivityBar active="chat" onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: /^files$/i }));
    expect(onSelect).toHaveBeenCalledWith("files");
  });

  it("does not promote Index as a primary activity", () => {
    render(<ActivityBar active="chat" onSelect={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /index/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^settings$/i })).toBeInTheDocument();
  });
});
