// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { KEYBOARD_SHORTCUTS } from "./keyboardHelp";

describe("KEYBOARD_SHORTCUTS", () => {
  it("lists the shell shortcuts as shortcut → action pairs", () => {
    const actions = KEYBOARD_SHORTCUTS.map((row) => row.action);
    expect(actions).toEqual(
      expect.arrayContaining([
        "New chat",
        "Toggle activity bar",
        "Toggle inspector",
        "Terminal",
        "Settings",
        "Close menus",
      ]),
    );
  });

  it("includes Ctrl/Cmd variants for the primary shortcuts", () => {
    const shortcuts = KEYBOARD_SHORTCUTS.map((row) => row.shortcut).join(" ");
    expect(shortcuts).toMatch(/Ctrl\+N|Cmd\+N/);
    expect(shortcuts).toMatch(/Ctrl\+B|Cmd\+B/);
    expect(shortcuts).toMatch(/Ctrl\+Shift\+J|Cmd\+Shift\+J/);
    expect(shortcuts).toMatch(/Ctrl\+`|Cmd\+`/);
    expect(shortcuts).toMatch(/Ctrl\+,|Cmd\+,/);
  });
});
