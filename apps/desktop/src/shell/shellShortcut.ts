// SPDX-License-Identifier: AGPL-3.0-or-later

export type ShellShortcut =
  | "new-chat"
  | "toggle-activity-bar"
  | "toggle-inspector"
  | "toggle-terminal"
  | "open-settings"
  | "go-to-file";

interface ShortcutKeys {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

export function shellShortcutFromKeyboard(event: ShortcutKeys): ShellShortcut | null {
  const modifier = event.metaKey || event.ctrlKey;
  if (!modifier || event.altKey) {
    return null;
  }
  const key = event.key.toLowerCase();
  if (key === "n" && !event.shiftKey) {
    return "new-chat";
  }
  if (key === "b" && !event.shiftKey) {
    return "toggle-activity-bar";
  }
  if (key === "j" && event.shiftKey) {
    return "toggle-inspector";
  }
  if (key === "`" && !event.shiftKey) {
    return "toggle-terminal";
  }
  if (key === "p" && !event.shiftKey) {
    return "go-to-file";
  }
  if (key === "," && !event.shiftKey) {
    return "open-settings";
  }
  return null;
}
