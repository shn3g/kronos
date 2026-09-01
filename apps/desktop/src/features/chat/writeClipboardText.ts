// SPDX-License-Identifier: AGPL-3.0-or-later

export async function writeClipboardText(text: string): Promise<boolean> {
  const clipboard = navigator.clipboard;
  if (!clipboard || typeof clipboard.writeText !== "function") {
    return false;
  }
  try {
    await clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
