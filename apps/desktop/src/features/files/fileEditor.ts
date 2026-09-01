// SPDX-License-Identifier: AGPL-3.0-or-later

export const SAVE_FILE_EVENT = "kronos-save-file";
export const FIND_IN_FILE_EVENT = "kronos-find-in-file";
export const REPLACE_IN_FILE_EVENT = "kronos-replace-in-file";

export interface FileFindMatch {
  start: number;
  end: number;
}

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

export function editorLineLabels(content: string): string[] {
  const count = content.split("\n").length;
  return Array.from({ length: Math.max(1, count) }, (_, index) => String(index + 1));
}

export function findInFileText(content: string, query: string): FileFindMatch[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") {
    return [];
  }
  const haystack = content.toLowerCase();
  const matches: FileFindMatch[] = [];
  let from = 0;
  while (from <= haystack.length) {
    const at = haystack.indexOf(needle, from);
    if (at < 0) {
      break;
    }
    matches.push({ start: at, end: at + needle.length });
    from = at + needle.length;
  }
  return matches;
}

export function nextFileFindIndex(current: number, delta: number, length: number): number {
  if (length <= 0) {
    return 0;
  }
  return (current + delta + length) % length;
}

export function fileFindStatusLabel(query: string, matchCount: number, activeIndex: number): string {
  if (query.trim() === "") {
    return "";
  }
  if (matchCount <= 0) {
    return "No matches.";
  }
  return `${activeIndex + 1} of ${matchCount}`;
}

export function replaceInFileMatch(
  content: string,
  match: FileFindMatch,
  replacement: string,
): { content: string; caret: number } {
  if (match.start < 0 || match.end < match.start || match.end > content.length) {
    return { content, caret: content.length };
  }
  return {
    content: `${content.slice(0, match.start)}${replacement}${content.slice(match.end)}`,
    caret: match.start + replacement.length,
  };
}

export function replaceAllInFileText(
  content: string,
  query: string,
  replacement: string,
): { content: string; count: number } {
  const matches = findInFileText(content, query);
  if (matches.length === 0) {
    return { content, count: 0 };
  }
  let next = "";
  let last = 0;
  for (const match of matches) {
    next += `${content.slice(last, match.start)}${replacement}`;
    last = match.end;
  }
  return { content: `${next}${content.slice(last)}`, count: matches.length };
}
