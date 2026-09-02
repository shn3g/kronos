// SPDX-License-Identifier: AGPL-3.0-or-later

export async function setDesktopWindowTitle(title: string): Promise<void> {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setTitle(title);
  } catch {
    return;
  }
}
