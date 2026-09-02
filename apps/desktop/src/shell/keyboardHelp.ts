// SPDX-License-Identifier: AGPL-3.0-or-later

export interface KeyboardShortcutRow {
  shortcut: string;
  action: string;
}

export const KEYBOARD_SHORTCUTS: KeyboardShortcutRow[] = [
  { shortcut: "Ctrl+N / Cmd+N", action: "New chat" },
  { shortcut: "Ctrl+B / Cmd+B", action: "Toggle activity bar" },
  { shortcut: "Ctrl+Shift+J / Cmd+Shift+J", action: "Toggle inspector" },
  { shortcut: "Ctrl+` / Cmd+`", action: "Terminal" },
  { shortcut: "Ctrl+P / Cmd+P", action: "Go to file" },
  { shortcut: "Ctrl+L / Cmd+L", action: "Ask in chat" },
  { shortcut: "Ctrl+Shift+F / Cmd+Shift+F", action: "Find in files" },
  { shortcut: "Ctrl+, / Cmd+,", action: "Settings" },
  { shortcut: "Escape", action: "Close menus" },
];
