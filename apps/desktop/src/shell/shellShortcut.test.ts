// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { shellShortcutFromKeyboard } from "./shellShortcut";

describe("shellShortcutFromKeyboard", () => {
  it("maps modifier shortcuts used by the desktop frame", () => {
    const base = { metaKey: false, ctrlKey: true, shiftKey: false, altKey: false };

    expect(shellShortcutFromKeyboard({ ...base, key: "n" })).toBe("new-chat");
    expect(shellShortcutFromKeyboard({ ...base, key: "b" })).toBe("toggle-activity-bar");
    expect(shellShortcutFromKeyboard({ ...base, key: ",", shiftKey: false })).toBe("open-settings");
    expect(
      shellShortcutFromKeyboard({ ...base, key: "j", shiftKey: true }),
    ).toBe("toggle-inspector");
    expect(shellShortcutFromKeyboard({ ...base, key: "`" })).toBe("toggle-terminal");
    expect(shellShortcutFromKeyboard({ ...base, key: "p" })).toBe("go-to-file");
  });

  it("ignores keys without a modifier and ignores Alt combinations", () => {
    expect(
      shellShortcutFromKeyboard({
        key: "n",
        metaKey: false,
        ctrlKey: false,
        shiftKey: false,
        altKey: false,
      }),
    ).toBeNull();
    expect(
      shellShortcutFromKeyboard({
        key: "n",
        metaKey: false,
        ctrlKey: true,
        shiftKey: false,
        altKey: true,
      }),
    ).toBeNull();
  });
});
