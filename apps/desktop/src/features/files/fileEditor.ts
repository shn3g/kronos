// SPDX-License-Identifier: AGPL-3.0-or-later

export const SAVE_FILE_EVENT = "kronos-save-file";

export function fileDraftIsDirty(saved: string | null, draft: string | null): boolean {
  if (saved === null || draft === null) {
    return false;
  }
  return saved !== draft;
}

export function insertEditorText(
  content: string,
  start: number,
  end: number,
  insertion: string,
): { content: string; caret: number } {
  const from = Math.max(0, Math.min(start, content.length));
  const to = Math.max(from, Math.min(end, content.length));
  return {
    content: `${content.slice(0, from)}${insertion}${content.slice(to)}`,
    caret: from + insertion.length,
  };
}
