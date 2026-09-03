// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { KEYBOARD_SHORTCUTS } from "./keyboardHelp";
import { MenuBar } from "./MenuBar";

const noop = () => undefined;

function renderMenuBar() {
  return render(
    <MenuBar
      historyOpen={false}
      activityCollapsed={false}
      inspectorCollapsed={false}
      terminalOpen={false}
      onNewChat={noop}
      onOpenFolder={noop}
      onGoToFile={noop}
      onFindInFile={noop}
      onFindInFiles={noop}
      onReplaceInFile={noop}
      onGoToLine={noop}
      onAskInChat={noop}
      onToggleHistory={noop}
      onToggleActivityBar={noop}
      onToggleInspector={noop}
      onToggleTerminal={noop}
      onOpenSettings={noop}
      onOpenModels={noop}
    />,
  );
}

describe("MenuBar Help", () => {
  it("shows a scannable keyboard map instead of a dense paragraph", async () => {
    const user = userEvent.setup();
    renderMenuBar();

    await user.click(screen.getByRole("menuitem", { name: /^Help$/ }));

    const list = screen.getByRole("list", { name: /keyboard shortcuts/i });
    for (const row of KEYBOARD_SHORTCUTS) {
      expect(screen.getByText(row.shortcut)).toBeInTheDocument();
      expect(screen.getByText(row.action)).toBeInTheDocument();
    }
    expect(list.querySelectorAll("li").length).toBe(KEYBOARD_SHORTCUTS.length);
    expect(screen.queryByText(/Ctrl\+N or Cmd\+N starts a new chat/i)).not.toBeInTheDocument();
  });
});
